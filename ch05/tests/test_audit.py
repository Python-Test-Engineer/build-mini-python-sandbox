"""Tests for the hash-chained audit log.

Run from ``ch05/``:

    python -m pytest -v
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
        self.temp = self.enterContext(tempfile.TemporaryDirectory(prefix="audit-test-"))
        self.path = Path(self.temp) / "audit" / "events.jsonl"
        self.log = AuditLog(self.path)

    def test_empty_log_verifies(self) -> None:
        self.assertEqual(self.log.events(), [])
        self.assertTrue(self.log.verify())

    def test_record_appends(self) -> None:
        self.log.record("tool.call", "requested", {"tool": "read_file"})
        self.log.record("tool.result", "ok", {"bytes": 10})
        events = self.log.events()
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["seq"], 1)
        self.assertEqual(events[1]["seq"], 2)
        self.assertTrue(self.log.verify())

    def test_reload_continues_chain(self) -> None:
        self.log.record("one", "ok", {})
        self.log.record("two", "ok", {})

        reopened = AuditLog(self.path)
        reopened.record("three", "ok", {})
        self.assertTrue(reopened.verify())
        self.assertEqual([event["seq"] for event in reopened.events()], [1, 2, 3])

    def test_tamper_is_detected(self) -> None:
        self.log.record("one", "ok", {"value": "a"})
        self.log.record("two", "ok", {"value": "b"})

        lines = self.path.read_text(encoding="utf-8").splitlines()
        first = json.loads(lines[0])
        first["detail"]["value"] = "edited"
        lines[0] = json.dumps(first, separators=(",", ":"))
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        self.assertFalse(self.log.verify())

    def test_deleted_middle_event_is_detected(self) -> None:
        for index in range(3):
            self.log.record(f"event-{index}", "ok", {})
        lines = self.path.read_text(encoding="utf-8").splitlines()
        self.path.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")
        self.assertFalse(self.log.verify())

    def test_secret_values_are_redacted(self) -> None:
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
        self.log.record("big", "ok", {"text": "x" * 2000})
        event = self.log.events()[0]
        self.assertLessEqual(len(event["detail"]["text"]), 520)
        self.assertIn("truncated", event["detail"]["text"])

    def test_malformed_log_raises(self) -> None:
        self.path.write_text("{not json}\n", encoding="utf-8")
        with self.assertRaises(AuditError):
            AuditLog(self.path)

    def test_tampered_existing_log_refuses_to_open(self) -> None:
        self.log.record("one", "ok", {})
        lines = self.path.read_text(encoding="utf-8").splitlines()
        event = json.loads(lines[0])
        event["outcome"] = "edited"
        self.path.write_text(json.dumps(event) + "\n", encoding="utf-8")
        with self.assertRaises(AuditError):
            AuditLog(self.path)


if __name__ == "__main__":
    unittest.main()
