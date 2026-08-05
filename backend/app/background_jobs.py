from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.database import SessionLocal
from app.models import BackgroundJob, BackgroundJobStatus
from app.resume_processing import process_application


def queue_application_analysis(db, application_id: str, organization_id: str | None, force: bool = False) -> BackgroundJob:
    job = BackgroundJob(organization_id=organization_id, job_type="application_analysis", payload={"application_id": application_id, "force": force})
    db.add(job)
    db.flush()
    return job


def run_background_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.scalar(select(BackgroundJob).where(BackgroundJob.id == job_id).with_for_update(skip_locked=True))
        if not job or job.status not in {BackgroundJobStatus.QUEUED, BackgroundJobStatus.FAILED}:
            return
        job.status = BackgroundJobStatus.RUNNING
        job.locked_at = datetime.now(UTC)
        job.attempts += 1
        db.commit()
        if job.job_type == "application_analysis":
            process_application(job.payload["application_id"], bool(job.payload.get("force")))
        job = db.get(BackgroundJob, job_id)
        job.status = BackgroundJobStatus.COMPLETED
        job.completed_at = datetime.now(UTC)
        job.last_error = None
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.get(BackgroundJob, job_id)
        if job:
            job.last_error = f"{type(exc).__name__}: {exc}"[:1000]
            if job.attempts < job.max_attempts:
                job.status = BackgroundJobStatus.QUEUED
                job.run_after = datetime.now(UTC) + timedelta(seconds=2 ** job.attempts)
            else:
                job.status = BackgroundJobStatus.FAILED
            db.commit()
    finally:
        db.close()


def run_next_queued_job() -> bool:
    db = SessionLocal()
    try:
        job = db.scalar(select(BackgroundJob).where(BackgroundJob.status == BackgroundJobStatus.QUEUED, BackgroundJob.run_after <= datetime.now(UTC)).order_by(BackgroundJob.created_at))
        if not job:
            return False
        job_id = job.id
    finally:
        db.close()
    run_background_job(job_id)
    return True
