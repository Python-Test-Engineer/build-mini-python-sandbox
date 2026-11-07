"""audit.py - an append-only, hash-chained record of agent actions.

The sandbox decides what is allowed. The audit log records what happened. Both
matter: a refusal that nobody can see is hard to debug, and an action that
nobody can reconstruct is hard to trust.

Design choices:

* **JSON Lines**: one event per line, easy to tail, grep and ship.
* **Append-only**: events are written with ``O_APPEND`` and never rewritten.
* **Hash chain**: each event includes the previous event's hash. Deleting or
  editing a line in the middle breaks ``verify()``.
* **Outside the workspace**: the model's file tools cannot edit the log. A
  determined local user still can; the chain makes tampering visible, not
  impossible.
* **Redaction**: values for keys that look secret are replaced before writing.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Key names that should never be written in clear text. The match is
# intentionally broad: ``api_key``, ``OPENROUTER_API_KEY``, ``token`` and
# ``password`` all redact.
_SECRET_KEY = re.compile(r"(key|token|secret|password|passwd|credential)", re.IGNORECASE)

# Long tool arguments are truncated in the audit. The audit is a trail, not a
# second copy of the workspace.
MAX_VALUE_CHARS = 500


def _redact(value: Any, key: str | None = None) -> Any:
    """Return a JSON-safe copy with secrets masked and long strings clipped."""
    if key is not None and _SECRET_KEY.search(key):
        return "***REDACTED***"

    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return value if len(value) <= MAX_VALUE_CHARS else value[:MAX_VALUE_CHARS] + "...[truncated]"
    if isinstance(value, (int, float, bool)) or value is None:
        return value

    # Paths and other objects become strings so the log always serialises.
    return _redact(str(value))


class AuditError(Exception):
    """The audit log is present but cannot be trusted or appended."""


class AuditLog:
    """A small hash-chained JSONL writer.

    The constructor reads the existing file to continue the chain. It is not
    intended for multiple processes writing the same log concurrently; the
    in-process lock protects threads, and the file is opened with ``O_APPEND``
    so a second process is at least not silently truncating it.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # 64 zeros is the conventional "no previous event" value. It keeps the
        # first event's hash shaped like every later one.
        self._previous_hash = "0" * 64
        self._sequence = 0
        self._lock = threading.Lock()

        if self.path.exists():
            self._load_tail()

    # -- public API --------------------------------------------------------

    def record(self, action: str, outcome: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
        """Append one event and return the event that was written."""
        with self._lock:
            self._sequence += 1
            event: dict[str, Any] = {
                "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "seq": self._sequence,
                "action": str(action),
                "outcome": str(outcome),
                "detail": _redact(detail or {}),
                "prev": self._previous_hash,
            }

            # Canonical JSON makes verification independent of key order.
            canonical = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            digest = hashlib.sha256((self._previous_hash + canonical).encode("utf-8")).hexdigest()
            event["hash"] = digest

            line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
            try:
                with open(self.path, "a", encoding="utf-8", newline="\n") as handle:
                    handle.write(line + "\n")
                    handle.flush()
                    # fsync makes the audit durable across a crash. It costs a
                    # little latency; for a book-scale harness that is fine.
                    os.fsync(handle.fileno())
            except OSError as exc:
                raise AuditError(f"could not append to audit log: {exc}") from exc

            self._previous_hash = digest
            return event

    def events(self) -> list[dict[str, Any]]:
        """Read every event. Malformed lines raise AuditError."""
        if not self.path.exists():
            return []

        result: list[dict[str, Any]] = []
        with open(self.path, "r", encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    result.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise AuditError(f"invalid JSON on line {number}: {exc}") from exc
        return result

    def verify(self) -> bool:
        """Recompute the chain and return False on any gap or edit."""
        events = self.events()
        previous = "0" * 64

        for expected_sequence, event in enumerate(events, start=1):
            if event.get("seq") != expected_sequence:
                return False
            if event.get("prev") != previous:
                return False

            stored_hash = event.get("hash")
            without_hash = {key: value for key, value in event.items() if key != "hash"}
            canonical = json.dumps(
                without_hash,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            computed = hashlib.sha256((previous + canonical).encode("utf-8")).hexdigest()
            if stored_hash != computed:
                return False
            previous = stored_hash

        return True

    # -- internals ---------------------------------------------------------

    def _load_tail(self) -> None:
        """Continue the sequence and chain from the last valid event."""
        events = self.events()
        if not events:
            return

        last = events[-1]
        self._sequence = int(last.get("seq", len(events)))
        self._previous_hash = str(last.get("hash", "0" * 64))

        # If the existing file is already broken, fail loudly now rather than
        # appending to a chain that cannot verify.
        if not self.verify():
            raise AuditError(f"existing audit log fails verification: {self.path}")
