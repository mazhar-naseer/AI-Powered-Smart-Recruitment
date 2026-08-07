import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import (
    Application, AuditLog, BillingEvent, Job, Organization, OrganizationMembership,
    OrganizationSubscription, Role, User,
)
from app.saas import PLAN_CATALOG, ensure_subscription, usage_snapshot
from app.security import require_roles
from app.tenancy import ensure_membership, require_permission
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1")
settings = get_settings()


def envelope(data=None, message="Success"):
    return {"success": True, "message": message, "data": data}


class WorkspaceSettingsUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    timezone: str = Field(default="UTC", min_length=2, max_length=80)
    company_domain: str | None = Field(default=None, max_length=180)
    careers_url: HttpUrl | None = None
    primary_color: str = Field(default="#173fbf", pattern=r"^#[0-9a-fA-F]{6}$")
    data_retention_days: int = Field(default=365, ge=30, le=3650)
    candidate_email_notifications: bool = True
    onboarding_completed: bool = False


class PlanChange(BaseModel):
    plan_key: str


def subscription_dict(item: OrganizationSubscription) -> dict:
    return {
        "plan_key": item.plan_key,
        "status": item.status,
        "billing_provider": item.billing_provider,
        "trial_ends_at": item.trial_ends_at.isoformat() if item.trial_ends_at else None,
        "current_period_end": item.current_period_end.isoformat() if item.current_period_end else None,
        "cancel_at_period_end": item.cancel_at_period_end,
    }


@router.get("/workspace/saas")
def workspace_saas(user: User = Depends(require_roles(Role.EMPLOYER)), db: Session = Depends(get_db)):
    membership = ensure_membership(db, user)
    organization = membership.organization
    subscription = ensure_subscription(db, organization.id)
    db.commit()
    settings_json = organization.settings_json or {}
    checklist = {
        "company_profile": bool(settings_json.get("company_domain") or user.company_website),
        "team_invited": (db.scalar(select(func.count(OrganizationMembership.id)).where(OrganizationMembership.organization_id == organization.id, OrganizationMembership.status == "active")) or 0) > 1,
        "job_published": (db.scalar(select(func.count(Job.id)).where(Job.organization_id == organization.id)) or 0) > 0,
        "onboarding_completed": bool(settings_json.get("onboarding_completed")),
    }
    return envelope({
        "organization": {"id": organization.id, "name": organization.name, "slug": organization.slug, "settings": settings_json},
        "subscription": subscription_dict(subscription),
        "plans": PLAN_CATALOG,
        "usage": usage_snapshot(db, organization.id),
        "onboarding": checklist,
    })


@router.patch("/workspace/settings")
def update_workspace_settings(payload: WorkspaceSettingsUpdate, user: User = Depends(require_roles(Role.EMPLOYER)), db: Session = Depends(get_db)):
    membership = ensure_membership(db, user)
    require_permission(db, user, "organization.manage", membership.organization_id)
    organization = membership.organization
    organization.name = payload.name.strip()
    organization.settings_json = {
        **(organization.settings_json or {}),
        **payload.model_dump(mode="json", exclude={"name"}),
    }
    db.add(AuditLog(actor_id=user.id, action="workspace.settings_updated", target_type="organization", target_id=organization.id))
    db.commit()
    return envelope({"name": organization.name, "settings": organization.settings_json}, "Workspace settings updated")


@router.post("/workspace/billing/change-plan")
def change_plan(payload: PlanChange, user: User = Depends(require_roles(Role.EMPLOYER)), db: Session = Depends(get_db)):
    membership = ensure_membership(db, user)
    require_permission(db, user, "organization.manage", membership.organization_id)
    if payload.plan_key not in PLAN_CATALOG:
        logger.warning("Plan change refused: %r is not a known plan", payload.plan_key)
        raise HTTPException(422, "Unknown subscription plan")
    if settings.billing_provider != "manual":
        logger.warning(
            "Manual plan change refused for organization %s: billing provider is %s",
            membership.organization_id,
            settings.billing_provider,
        )
        raise HTTPException(409, "Use the configured billing provider checkout to change this plan")
    subscription = ensure_subscription(db, membership.organization_id)
    now = datetime.now(UTC)
    subscription.plan_key = payload.plan_key
    subscription.status = "active"
    subscription.current_period_start = now
    subscription.current_period_end = now + timedelta(days=30)
    subscription.trial_ends_at = None
    db.add(AuditLog(actor_id=user.id, action="billing.plan_changed", target_type="organization", target_id=membership.organization_id, metadata_json={"plan": payload.plan_key, "provider": "manual"}))
    db.commit()
    logger.info(
        "Organization %s moved to plan %s by user %s (manual billing)",
        membership.organization_id,
        payload.plan_key,
        user.id,
    )
    return envelope(subscription_dict(subscription), "Plan changed in manual billing mode")


@router.get("/workspace/data-export")
def workspace_export(user: User = Depends(require_roles(Role.EMPLOYER)), db: Session = Depends(get_db)):
    membership = ensure_membership(db, user)
    require_permission(db, user, "organization.manage", membership.organization_id)
    organization = membership.organization
    jobs = db.scalars(select(Job).where(Job.organization_id == organization.id)).all()
    applications = db.scalars(select(Application).where(Application.organization_id == organization.id)).all()
    db.add(AuditLog(actor_id=user.id, action="privacy.workspace_exported", target_type="organization", target_id=organization.id))
    db.commit()
    # A full export of a workspace's jobs and applications is exactly the event a
    # later privacy or incident review needs to be able to find.
    logger.info(
        "User %s exported organization %s: %d jobs, %d applications",
        user.id,
        organization.id,
        len(jobs),
        len(applications),
    )
    return envelope({
        "exported_at": datetime.now(UTC).isoformat(),
        "organization": {"id": organization.id, "name": organization.name, "slug": organization.slug, "settings": organization.settings_json},
        "jobs": [{"id": job.id, "title": job.title, "status": job.status.value, "created_at": job.created_at.isoformat()} for job in jobs],
        "applications": [{"id": item.id, "job_id": item.job_id, "status": item.status.value, "score": item.override_score if item.override_score is not None else item.final_score, "created_at": item.created_at.isoformat()} for item in applications],
    })


@router.post("/billing/webhooks/{provider}")
async def billing_webhook(provider: str, request: Request, x_smarthire_billing_signature: str | None = Header(default=None), db: Session = Depends(get_db)):
    body = await request.body()
    if not settings.billing_webhook_secret:
        logger.error("Billing webhook from %s rejected: no webhook secret is configured", provider)
        raise HTTPException(503, "Billing webhooks are not configured")
    expected = hmac.new(settings.billing_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    if not x_smarthire_billing_signature or not hmac.compare_digest(expected, x_smarthire_billing_signature):
        # Neither signature is logged: the expected value is derived from the
        # shared secret, and printing it would hand an attacker a valid one.
        logger.warning(
            "Billing webhook from %s rejected: signature %s",
            provider,
            "missing" if not x_smarthire_billing_signature else "does not match",
        )
        raise HTTPException(401, "Invalid billing webhook signature")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        # A signed body that is not JSON means the provider and this handler
        # disagree about the format — a 400 the sender can act on, not a 500.
        logger.warning("Billing webhook from %s carried a signed but unparsable body", provider)
        raise HTTPException(400, "Billing webhook body is not valid JSON") from None
    if not isinstance(payload, dict):
        logger.warning("Billing webhook from %s sent a %s where an object was expected", provider, type(payload).__name__)
        raise HTTPException(422, "Billing event must be a JSON object")
    event_id = str(payload.get("id", ""))
    event_type = str(payload.get("type", ""))
    if not event_id or not event_type:
        logger.warning("Billing webhook from %s is missing an event id or type", provider)
        raise HTTPException(422, "Billing event id and type are required")
    if db.scalar(select(BillingEvent).where(BillingEvent.provider_event_id == event_id)):
        logger.info("Billing event %s from %s already processed, ignoring replay", event_id, provider)
        return envelope(message="Billing event already processed")
    db.add(BillingEvent(provider=provider, provider_event_id=event_id, event_type=event_type, payload=payload))
    data = payload.get("data", {})
    organization_id = data.get("organization_id")
    if organization_id and event_type == "subscription.updated":
        subscription = ensure_subscription(db, organization_id)
        if data.get("plan_key") in PLAN_CATALOG:
            subscription.plan_key = data["plan_key"]
        elif data.get("plan_key") is not None:
            logger.warning(
                "Billing event %s named unknown plan %r, keeping %s",
                event_id,
                data.get("plan_key"),
                subscription.plan_key,
            )
        subscription.status = data.get("status", subscription.status)
        subscription.external_customer_id = data.get("customer_id", subscription.external_customer_id)
        subscription.external_subscription_id = data.get("subscription_id", subscription.external_subscription_id)
        logger.info(
            "Billing event %s updated organization %s to plan %s (status=%s)",
            event_id,
            organization_id,
            subscription.plan_key,
            subscription.status,
        )
    db.commit()
    logger.info("Processed billing event %s (%s) from %s", event_id, event_type, provider)
    return envelope(message="Billing event processed")


@router.get("/admin/saas/overview")
def admin_saas_overview(_user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    subscriptions = db.scalars(select(OrganizationSubscription)).all()
    distribution = {key: 0 for key in PLAN_CATALOG}
    for item in subscriptions:
        distribution[item.plan_key] = distribution.get(item.plan_key, 0) + 1
    mrr = sum(PLAN_CATALOG.get(item.plan_key, PLAN_CATALOG["starter"])["monthly_price"] for item in subscriptions if item.status in {"active", "trialing"})
    organizations = db.scalars(select(Organization).order_by(Organization.created_at.desc())).all()
    return envelope({
        "organizations": len(organizations),
        "active_subscriptions": sum(item.status in {"active", "trialing"} for item in subscriptions),
        "estimated_mrr": mrr,
        "plan_distribution": distribution,
        "accounts": [{"id": org.id, "name": org.name, "status": org.status, "plan": next((item.plan_key for item in subscriptions if item.organization_id == org.id), "starter")} for org in organizations],
    })
