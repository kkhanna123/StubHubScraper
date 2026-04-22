"""One-shot collection run (useful for local smoke tests)."""
import logging
from src.scheduler import run_cycle

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_cycle()
