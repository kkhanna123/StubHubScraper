"""Storage backends for StubHub listings snapshots."""
from __future__ import annotations

import atexit
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from .config import DATA_DIR, DUCKDB_PATH, DUCKDB_TABLE, STORAGE_BACKEND
from .discovery import Event

log = logging.getLogger(__name__)


def event_parquet_path(event: Event) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / f"event_{event.event_id}"


def append_rows(event: Event, rows: list[dict[str, Any]]) -> Path | None:
    """Append snapshot rows to the configured storage backend."""
    sink = _get_sink()
    if not rows:
        return sink.empty_result(event)
    return sink.append_rows(event, rows)


class _StorageSink:
    def append_rows(self, event: Event, rows: list[dict[str, Any]]) -> Path | None:
        raise NotImplementedError

    def empty_result(self, event: Event) -> Path | None:
        del event
        return None

    def close(self) -> None:
        return None


class ParquetStorageSink(_StorageSink):
    """Original filesystem-backed parquet storage."""

    def empty_result(self, event: Event) -> Path:
        return event_parquet_path(event)

    def append_rows(self, event: Event, rows: list[dict[str, Any]]) -> Path:
        path = event_parquet_path(event)
        path.mkdir(parents=True, exist_ok=True)
        new = pd.DataFrame(_prepare_rows(event, rows))
        snapshot_label = rows[0]["snapshot_ts"].strftime("%Y%m%dT%H%M%S%fZ")
        part_path = path / f"snapshot_{snapshot_label}_{uuid4().hex[:8]}.parquet"
        new.to_parquet(part_path, index=False)
        log.info(
            "event %s: wrote %d new rows -> %s",
            event.event_id,
            len(new),
            part_path,
        )
        return path


class DuckDBStorageSink(_StorageSink):
    def __init__(self, path: Path, table: str):
        try:
            import duckdb
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("DuckDB storage requires the 'duckdb' package to be installed.") from exc

        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._table = table
        self._conn = duckdb.connect(str(path))

    def append_rows(self, event: Event, rows: list[dict[str, Any]]) -> Path:
        frame = pd.DataFrame(_prepare_rows(event, rows))
        self._conn.register("stubhub_new_rows", frame)
        try:
            self._conn.execute(
                f"CREATE TABLE IF NOT EXISTS {_quoted_identifier(self._table)} "
                "AS SELECT * FROM stubhub_new_rows LIMIT 0"
            )
            self._conn.execute(
                f"INSERT INTO {_quoted_identifier(self._table)} BY NAME SELECT * FROM stubhub_new_rows"
            )
        finally:
            self._conn.unregister("stubhub_new_rows")
        log.info(
            "event %s: wrote %d rows into DuckDB table %s (%s)",
            event.event_id,
            len(frame),
            self._table,
            self._path,
        )
        return self._path

    def close(self) -> None:
        self._conn.close()


def _prepare_rows(event: Event, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    event_payload = {
        "event_slug": event.slug,
        "event_name": event.name,
        "venue_name": event.venue_name,
        "venue_city": event.venue_city,
        "event_start_utc": event.start_utc.isoformat(),
        "event_end_utc": event.end_utc.isoformat(),
        "category_id": event.category_id,
        "formatted_date": event.formatted_date,
        "formatted_time": event.formatted_time,
        "day_of_week": event.day_of_week,
    }
    return [{**event_payload, **row} for row in rows]


def _quoted_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _build_sink() -> _StorageSink:
    if STORAGE_BACKEND == "parquet":
        return ParquetStorageSink()
    if STORAGE_BACKEND == "duckdb":
        return DuckDBStorageSink(path=DUCKDB_PATH, table=DUCKDB_TABLE)
    raise ValueError(f"Unsupported STUBHUB_STORAGE_BACKEND: {STORAGE_BACKEND!r}")


_sink: _StorageSink | None = None


def _get_sink() -> _StorageSink:
    global _sink
    if _sink is None:
        _sink = _build_sink()
    return _sink


def _close_sink() -> None:
    if _sink is not None:
        _sink.close()


atexit.register(_close_sink)
