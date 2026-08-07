"""Run SmartHire's durable background-job worker as a separate process."""

import time

from app.background_jobs import run_next_queued_job
from app.logging_config import get_logger

logger = get_logger("app.worker")


if __name__ == "__main__":
    logger.info("SmartHire worker started")
    while True:
        if not run_next_queued_job():
            time.sleep(2)
