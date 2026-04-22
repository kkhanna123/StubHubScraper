from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.discovery import Event
from src.storage import ParquetStorageSink
import src.storage as storage_module


def _event(start_hour: int, end_hour: int) -> Event:
    return Event(
        event_id=158170204,
        name="Madrid Open",
        url="https://example.com/event",
        venue_name="Estadio Manolo Santana",
        venue_city="Madrid",
        start_utc=datetime(2026, 4, 22, start_hour, 0, tzinfo=timezone.utc),
        end_utc=datetime(2026, 4, 22, end_hour, 0, tzinfo=timezone.utc),
        category_id=4409,
        day_of_week="Wed",
        formatted_date="Apr 22",
        formatted_time="9:00 AM",
    )


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_data_dir = storage_module.DATA_DIR
        storage_module.DATA_DIR = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        storage_module.DATA_DIR = self.original_data_dir
        self.temp_dir.cleanup()

    def test_storage_key_is_stable_when_event_times_shift(self) -> None:
        sink = ParquetStorageSink()
        first_event = _event(9, 19)
        shifted_event = _event(10, 20)

        first_rows = [{"row_type": "summary", "snapshot_ts": datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc)}]
        second_rows = [{"row_type": "summary", "snapshot_ts": datetime(2026, 4, 21, 11, 0, tzinfo=timezone.utc)}]

        first_path = sink.append_rows(first_event, first_rows)
        second_path = sink.append_rows(shifted_event, second_rows)

        self.assertEqual(first_path, second_path)
        self.assertEqual(first_path, Path(self.temp_dir.name) / "event_158170204")
        self.assertEqual(len(list(first_path.glob("snapshot_*.parquet"))), 2)

    def test_parquet_appends_as_dataset_parts(self) -> None:
        sink = ParquetStorageSink()
        event = _event(9, 19)

        sink.append_rows(
            event,
            [{"row_type": "summary", "snapshot_ts": datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc), "value": 1}],
        )
        path = sink.append_rows(
            event,
            [{"row_type": "summary", "snapshot_ts": datetime(2026, 4, 21, 11, 0, tzinfo=timezone.utc), "value": 2}],
        )

        parts = sorted(path.glob("snapshot_*.parquet"))
        self.assertEqual(len(parts), 2)

        frame = pd.read_parquet(path).sort_values("value")
        self.assertEqual(frame["value"].tolist(), [1, 2])


if __name__ == "__main__":
    unittest.main()
