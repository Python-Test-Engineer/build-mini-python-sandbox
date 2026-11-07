"""Tests for the hash-chained audit log.

Run from ``ch05/``:

    python -m pytest -v

The audit log is append-only JSONL where each event contains the previous
event's hash. That chain is what makes tampering detectable:

* changing a field changes the event's own hash,
* deleting an event breaks the link from the next event,
* editing an old event invalidates every later ``prev`` hash.

The tests deliberately tamper with the file and assert that ``verify()``
returns ``False`` (or that opening the log raises). They also check the
privacy features: secret-looking values are redacted and long values are
truncated before they reach disk.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mini_harness.audit import AuditError, AuditLog


class AuditLogTests(unittest.TestCase):
    """Each test gets its own log file."""

    def setUp(self) -> None:
        # A private directory per test means no shared audit state can leak.
        self.temp = self.enterContext(tempfile.TemporaryDirectory(prefix="audit-test-"))
        self.path = Path(self.temp) / "audit" / "events.jsonl"
        self.log = AuditLog(self.path)

    def test_empty_log_verifies(self) -> None:
        """An empty log has no events and a valid (empty) chain."""
        self.assertEqual(self.log.events(), [])
        self.assertTrue(self.log.verify())

    def test_record_appends(self) -> None:
        """Recording assigns increasing sequence numbers and keeps the chain valid.

        ``seq`` is a simple, human-readable position that also makes missing
        events obvious when reading the file.
        """
        self.log.record("tool.call", "requested", {"tool": "read_file"})
        self.log.record("tool.result", "ok", {"bytes": 10})

        events = self.log.events()
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["seq"], 1)
        self.assertEqual(events[1]["seq"], 2)
        self.assertTrue(self.log.verify())

    def test_reload_continues_chain(self) -> None:
        """Reopening an existing log continues the chain instead of restarting it.

        A new ``AuditLog`` must read the last event's hash, so the next record
        links to the old history. The final chain must still verify and the
        sequence numbers must carry on from 1 to 3.
        """
        self.log.record("one", "ok", {})
        self.log.record("two", "ok", {})

        reopened = AuditLog(self.path)
        reopened.record("three", "ok", {})
        self.assertTrue(reopened.verify())
        self.assertEqual([event["seq"] for event in reopened.events()], [1, 2, 3])

    def test_tamper_is_detected(self) -> None:
        """Editing a recorded value breaks verification.

        We rewrite the first line with a different ``detail.value``. Because the
        event's hash no longer matches its contents, ``verify`` returns
        ``False``.
        """
        self.log.record("one", "ok", {"value": "a"})
        self.log.record("two", "ok", {"value": "b"})

        lines = self.path.read_text(encoding="utf-8").splitlines()
        first = json.loads(lines[0])
        first["detail"]["value"] = "edited"
        lines[0] = json.dumps(first, separators=(",", ":"))
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        self.assertFalse(self.log.verify())

    def test_deleted_middle_event_is_detected(self) -> None:
        """Removing an event from the middle breaks the hash link.

        We keep the first and third lines but drop the second. The third event
        still points at the missing event's hash, so verification fails.
        """
        for index in range(3):
            self.log.record(f"event-{index}", "ok", {})

        lines = self.path.read_text(encoding="utf-8").splitlines()
        self.path.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")
        self.assertFalse(self.log.verify())

    def test_secret_values_are_redacted(self) -> None:
        """Fields that look like secrets are replaced before writing.

        Both a top-level ``api_key`` and a nested ``token`` are redacted, while
        a harmless value stays visible. This keeps credentials out of logs even
        when a tool passes them through.
        """
        self.log.record(
            "config",
            "ok",
            {"api_key": "sk-secret", "nested": {"token": "abc"}, "safe": "visible"},
        )
        text = self.path.read_text(encoding="utf-8")
        self.assertNotIn("sk-secret", text)
        self.assertNotIn("abc", text)
        self.assertIn("***REDACTED***", text)
        self.assertIn("visible", text)

    def test_long_values_are_truncated(self) -> None:
        """Very long values are shortened and marked as truncated.

        A 2000-character value is capped at roughly 520 characters. The marker
        tells a reader that data was removed, rather than making the log look
        complete.
        """
        self.log.record("big", "ok", {"text": "x" * 2000})
        event = self.log.events()[0]
        self.assertLessEqual(len(event["detail"]["text"]), 520)
        self.assertIn("truncated", event["detail"]["text"])

    def test_malformed_log_raises(self) -> None:
        """A file that is not valid JSON is refused at open time.

        Starting a new run on top of a corrupt log would produce a chain that
        can never verify, so the constructor raises ``AuditError`` instead.
        """
        self.path.write_text("{not json}\n", encoding="utf-8")
        with self.assertRaises(AuditError):
            AuditLog(self.path)

    def test_tampered_existing_log_refuses_to_open(self) -> None:
        """Opening an already-tampered log fails loudly.

        Here the recorded ``outcome`` is changed. The hash no longer matches,
        and ``AuditLog`` refuses to continue appending to a broken history.
        """
        self.log.record("one", "ok", {})

        lines = self.path.read_text(encoding="utf-8").splitlines()
        event = json.loads(lines[0])
        event["outcome"] = "edited"
        self.path.write_text(json.dumps(event) + "\n", encoding="utf-8")

        with self.assertRaises(AuditError):
            AuditLog(self.path)


if __name__ == "__main__":
    unittest.main()
