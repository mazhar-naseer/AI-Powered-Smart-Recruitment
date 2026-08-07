import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.models import BackgroundJob, BackgroundJobStatus
from app.resume_processing import process_application
from app.logging_config import get_logger


logger = get_logger(__name__)

def queue_application_analysis(db, application_id: str, organization_id: str | None, force: bool = False) -> BackgroundJob:
    job = BackgroundJob(organization_id=organization_id, job_type="application_analysis", payload={"application_id": application_id, "force": force})
    db.add(job)
    db.flush()
    logger.info("Queued analysis job %s for application %s (force=%s)", job.id, application_id, force)
    return job


def run_background_job(job_id: str) -> None:
    started = time.perf_counter()
    db = SessionLocal()
    try:
        job = db.scalar(select(BackgroundJob).where(BackgroundJob.id == job_id).with_for_update(skip_locked=True))
        if not job or job.status not in {BackgroundJobStatus.QUEUED, BackgroundJobStatus.FAILED}:
            # Normal under concurrency: another worker claimed it first. Debug,
            # not warning, or every multi-worker deployment logs noise.
            logger.debug("Job %s skipped: already claimed or not runnable", job_id)
            return
        job.status = BackgroundJobStatus.RUNNING
        job.locked_at = datetime.now(UTC)
        job.attempts += 1
        job_type, attempt = job.job_type, job.attempts
        db.commit()
        logger.info("Running job %s (%s), attempt %d", job_id, job_type, attempt)
        if job.job_type == "application_analysis":
            process_application(job.payload["application_id"], bool(job.payload.get("force")))
        job = db.get(BackgroundJob, job_id)
        job.status = BackgroundJobStatus.COMPLETED
        job.completed_at = datetime.now(UTC)
        job.last_error = None
        db.commit()
        logger.info("Job %s completed in %.2fs", job_id, time.perf_counter() - started)
    except Exception as exc:
        db.rollback()
        job = db.get(BackgroundJob, job_id)
        if job:
            job.last_error = f"{type(exc).__name__}: {exc}"[:1000]
            if job.attempts < job.max_attempts:
                job.status = BackgroundJobStatus.QUEUED
                job.run_after = datetime.now(UTC) + timedelta(seconds=2 ** job.attempts)
                # Warning, not error: a retry is still pending, so this is not yet
                # a lost job.
                logger.warning(
                    "Job %s failed on attempt %d/%d, retrying after %ds: %s",
                    job_id,
                    job.attempts,
                    job.max_attempts,
                    2 ** job.attempts,
                    exc,
                )
            else:
                job.status = BackgroundJobStatus.FAILED
                # Terminal: nothing will pick this up again, so the traceback has
                # to be here or the cause is gone for good.
                logger.exception(
                    "Job %s failed permanently after %d attempts", job_id, job.attempts
                )
            db.commit()
        else:
            logger.exception("Job %s failed and its row no longer exists", job_id)
    finally:
        db.close()


def run_next_queued_job() -> bool:
    """Claim and run the oldest due job. Returns whether one was found.

    Never raises: the worker calls this in a bare loop, so an exception escaping
    here would end the process and stop every future job, not just this one.
    """
    db = SessionLocal()
    try:
        job = db.scalar(select(BackgroundJob).where(BackgroundJob.status == BackgroundJobStatus.QUEUED, BackgroundJob.run_after <= datetime.now(UTC)).order_by(BackgroundJob.created_at))
        if not job:
            return False
        job_id = job.id
    except SQLAlchemyError:
        logger.exception("Could not read the job queue")
        return False
    finally:
        db.close()
    try:
        run_background_job(job_id)
    except Exception:
        # run_background_job handles its own failures, but the recovery path in its
        # except block commits, and that commit can fail too — on a dropped
        # connection, for instance. Without this the worker process would exit and
        # every later job would stop, so the guarantee in the docstring above has
        # to be enforced here rather than assumed.
        logger.exception("Job %s escaped its own error handling", job_id)
    return True
