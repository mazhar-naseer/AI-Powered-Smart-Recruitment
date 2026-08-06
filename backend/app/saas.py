from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Job, JobStatus, OrganizationMembership, OrganizationSubscription, UsageCounter

settings = get_settings()

PLAN_CATALOG = {
    "starter": {
        "name": "Starter",
        "monthly_price": 0,
        "description": "For small teams validating their hiring workflow.",
        "limits": {"active_jobs": 3, "team_members": 3, "ai_analyses_monthly": 50, "storage_mb": 500},
    },
    "growth": {
        "name": "Growth",
        "monthly_price": 99,
        "description": "For growing recruiting teams with active pipelines.",
        "limits": {"active_jobs": 25, "team_members": 15, "ai_analyses_monthly": 1500, "storage_mb": 10000},
    },
    "scale": {
        "name": "Scale",
        "monthly_price": 299,
        "description": "For high-volume hiring with advanced governance.",
        "limits": {"active_jobs": None, "team_members": None, "ai_analyses_monthly": None, "storage_mb": 100000},
    },
}


def period_key() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def ensure_subscription(db: Session, organization_id: str) -> OrganizationSubscription:
    subscription = db.scalar(select(OrganizationSubscription).where(OrganizationSubscription.organization_id == organization_id))
    if subscription:
        return subscription
    now = datetime.now(UTC)
    subscription = OrganizationSubscription(
        organization_id=organization_id,
        plan_key="starter",
        status="trialing",
        billing_provider=settings.billing_provider,
        trial_ends_at=now + timedelta(days=settings.trial_days),
        current_period_start=now,
        current_period_end=now + timedelta(days=settings.trial_days),
    )
    db.add(subscription)
    db.flush()
    return subscription


def limit_for(subscription: OrganizationSubscription, metric: str) -> int | None:
    return PLAN_CATALOG.get(subscription.plan_key, PLAN_CATALOG["starter"])["limits"].get(metric)


def current_usage(db: Session, organization_id: str, metric: str) -> int:
    if metric == "active_jobs":
        return db.scalar(select(func.count(Job.id)).where(Job.organization_id == organization_id, Job.status == JobStatus.OPEN)) or 0
    if metric == "team_members":
        return db.scalar(select(func.count(OrganizationMembership.id)).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.status == "active")) or 0
    return db.scalar(select(UsageCounter.quantity).where(UsageCounter.organization_id == organization_id, UsageCounter.metric == metric, UsageCounter.period_key == period_key())) or 0


def enforce_limit(db: Session, organization_id: str, metric: str, increment: int = 1) -> None:
    subscription = ensure_subscription(db, organization_id)
    limit = limit_for(subscription, metric)
    if limit is not None and current_usage(db, organization_id, metric) + increment > limit:
        raise HTTPException(402, {"code": "PLAN_LIMIT_REACHED", "metric": metric, "limit": limit, "plan": subscription.plan_key})


def increment_usage(db: Session, organization_id: str, metric: str, quantity: int = 1) -> int:
    key = period_key()
    counter = db.scalar(select(UsageCounter).where(UsageCounter.organization_id == organization_id, UsageCounter.metric == metric, UsageCounter.period_key == key))
    if not counter:
        counter = UsageCounter(organization_id=organization_id, metric=metric, period_key=key, quantity=0)
        db.add(counter)
    counter.quantity += quantity
    db.flush()
    return counter.quantity


def usage_snapshot(db: Session, organization_id: str) -> dict:
    subscription = ensure_subscription(db, organization_id)
    metrics = ("active_jobs", "team_members", "ai_analyses_monthly", "storage_mb")
    return {
        metric: {"used": current_usage(db, organization_id, metric), "limit": limit_for(subscription, metric)}
        for metric in metrics
    }
