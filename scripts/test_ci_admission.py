#!/usr/bin/env python3
"""Deterministic unit tests for the CI admission cooldown boundary."""
from datetime import datetime, timedelta, timezone
import unittest

from ci_admission import admission_decision, parse_timestamp


class AdmissionDecisionTests(unittest.TestCase):
    def setUp(self):
        self.last = datetime(2026, 11, 3, 9, 0, 0, tzinfo=timezone.utc)

    def test_first_run_is_admitted(self):
        self.assertEqual(admission_decision(self.last, None), (True, 0))

    def test_299_seconds_is_rejected(self):
        event = self.last + timedelta(seconds=299)
        admitted, remaining = admission_decision(event, self.last)
        self.assertFalse(admitted)
        self.assertEqual(remaining, 1)

    def test_exactly_300_seconds_is_admitted(self):
        event = self.last + timedelta(seconds=300)
        self.assertEqual(admission_decision(event, self.last), (True, 0))

    def test_more_than_300_seconds_is_admitted(self):
        event = self.last + timedelta(seconds=301)
        self.assertEqual(admission_decision(event, self.last), (True, 0))

    def test_event_queued_before_marker_is_rejected(self):
        event = self.last - timedelta(seconds=1)
        admitted, remaining = admission_decision(event, self.last)
        self.assertFalse(admitted)
        self.assertGreaterEqual(remaining, 300)

    def test_timezone_offsets_are_normalized(self):
        parsed = parse_timestamp("2026-11-03T17:00:00+08:00")
        self.assertEqual(parsed, datetime(2026, 11, 3, 9, 0, 0, tzinfo=timezone.utc))

    def test_naive_timestamps_are_rejected(self):
        with self.assertRaises(ValueError):
            parse_timestamp("2026-11-03T09:00:00")


if __name__ == "__main__":
    unittest.main(verbosity=2)
