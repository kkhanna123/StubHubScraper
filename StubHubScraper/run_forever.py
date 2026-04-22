"""Main entrypoint for 24/7 server deployment.

Runs a collection cycle every hour until interrupted; survives per-cycle
exceptions and stops polling events whose `end_utc` is in the past.

Usage:
    python run_forever.py
"""
import logging
from pathlib import Path

from src.config import LOG_DIR
from src.scheduler import run_forever

if __name__ == "__main__":
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_DIR / "scraper.log"),
        ],
    )
    run_forever()
