from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.scheduler import _seconds_until_next_cycle


class SchedulerTests(unittest.TestCase):
    def test_seconds_until_next_hour_boundary(self) -> None:
        now = datetime(2026, 4, 21, 10, 17, 0, tzinfo=timezone.utc)
        self.assertEqual(_seconds_until_next_cycle(now, 3600), 43 * 60)

    def test_exact_boundary_waits_full_interval(self) -> None:
        now = datetime(2026, 4, 21, 10, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(_seconds_until_next_cycle(now, 3600), 3600)


if __name__ == "__main__":
    unittest.main()
