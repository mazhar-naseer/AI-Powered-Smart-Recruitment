"""Run SmartHire's durable background-job worker as a separate process."""

import time

from app.background_jobs import run_next_queued_job


if __name__ == "__main__":
    print("SmartHire worker started")
    while True:
        if not run_next_queued_job():
            time.sleep(2)
