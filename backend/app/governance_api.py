import csv
import io
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.database import get_db
from app.models import (AuditLog, MembershipRole, Organization, OrganizationMembership,
                        OrganizationSubscription, RefreshSession, Role, User, UserStatus)
from app.saas import PLAN_CATALOG, ensure_subscription
from app.security import require_roles
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/admin/governance")
settings = get_settings()


def envelope(data=None, message="Success"):
    return {"success": True, "message": message, "data": data}


def record(db: Session, admin: User, action: str, target_type: str, target_id: str, metadata: dict | None = None):
    db.add(AuditLog(actor_id=admin.id, action=action, target_type=target_type, target_id=target_id, metadata_json=metadata or {}))
    # Every mutating endpoint in this router calls record(), so logging here covers
    # all of them from one place. These are platform-privilege changes: the audit
    # table is authoritative, but a log line survives a rolled-back transaction
    # and reaches log aggregation, which the table does not.
    logger.info(
        "Admin %s performed %s on %s %s%s",
        admin.id,
        action,
        target_type,
        target_id,
        f" ({metadata})" if metadata else "",
    )


class PlatformRoleChange(BaseModel):
    role: Role
    confirmation: str


class MembershipCreate(BaseModel):
    user_id: str
    role: MembershipRole = MembershipRole.RECRUITER


class MembershipChange(BaseModel):
    role: MembershipRole


class OrganizationStateChange(BaseModel):
    status: str
    confirmation: str


class SubscriptionChange(BaseModel):
    plan_key: str
    status: str = "active"
    confirmation: str


@router.get("/overview")
def overview(_admin: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    organizations = db.scalars(select(Organization).order_by(Organization.name)).all()
    memberships = db.scalars(select(OrganizationMembership).options(joinedload(OrganizationMembership.user))).all()
    grouped: dict[str, list[dict]] = {}
    for item in memberships:
        grouped.setdefault(item.organization_id, []).append({"id": item.id, "role": item.role.value, "status": item.status, "user": {"id": item.user.id, "full_name": item.user.full_name, "email": item.user.email, "role": item.user.role.value}})
    subscriptions = {item.organization_id: item for item in db.scalars(select(OrganizationSubscription)).all()}
    return envelope({
        "plans": PLAN_CATALOG,
        "organizations": [{"id": org.id, "name": org.name, "slug": org.slug, "status": org.status,
                           "members": grouped.get(org.id, []),
                           "subscription": {"plan_key": subscriptions[org.id].plan_key, "status": subscriptions[org.id].status} if org.id in subscriptions else {"plan_key": "starter", "status": "trialing"}}
                          for org in organizations],
        "configuration": {"environment": settings.environment, "billing_provider": settings.billing_provider,
                          "smtp_configured": bool(settings.smtp_host), "google_oauth_configured": bool(settings.google_client_id),
                          "inline_background_jobs": settings.inline_background_jobs},
    })


@router.patch("/users/{user_id}/role")
def change_platform_role(user_id: str, payload: PlatformRoleChange, admin: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if not target or target.status == UserStatus.DELETED:
        raise HTTPException(404, "User not found")
    if target.id == admin.id:
        raise HTTPException(409, "You cannot change your own platform role")
    if payload.confirmation != target.email:
        raise HTTPException(422, "Enter the user's exact email address to confirm this role change")
    previous = target.role
    if previous == Role.ADMIN and payload.role != Role.ADMIN:
        admin_count = db.scalar(select(func.count(User.id)).where(User.role == Role.ADMIN, User.status == UserStatus.ACTIVE)) or 0
        if admin_count <= 1:
            raise HTTPException(409, "The last active platform administrator cannot be demoted")
    target.role = payload.role
    if payload.role != Role.EMPLOYER:
        target.active_organization_id = None
    for session in db.scalars(select(RefreshSession).where(RefreshSession.user_id == target.id, RefreshSession.revoked_at.is_(None))).all():
        session.revoked_at = datetime.now(UTC)
    record(db, admin, "governance.platform_role_changed", "user", target.id, {"previous_role": previous.value, "role": payload.role.value})
    db.commit()
    return envelope({"id": target.id, "role": target.role.value}, "Platform role updated; existing sessions were revoked")


@router.post("/organizations/{organization_id}/members", status_code=201)
def add_member(organization_id: str, payload: MembershipCreate, admin: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    organization, target = db.get(Organization, organization_id), db.get(User, payload.user_id)
    if not organization or not target:
        raise HTTPException(404, "Organization or user not found")
    if target.role != Role.EMPLOYER:
        raise HTTPException(422, "Only employer accounts can be assigned to recruiter workspaces")
    existing = db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_id == target.id))
    if existing:
        existing.status, existing.role = "active", payload.role
        membership = existing
    else:
        membership = OrganizationMembership(organization_id=organization_id, user_id=target.id, role=payload.role)
        db.add(membership)
    if not target.active_organization_id:
        target.active_organization_id = organization_id
    record(db, admin, "governance.membership_assigned", "organization", organization_id, {"user_id": target.id, "role": payload.role.value})
    db.commit()
    return envelope({"id": membership.id}, "Workspace membership assigned")


@router.patch("/memberships/{membership_id}")
def change_membership(membership_id: str, payload: MembershipChange, admin: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    item = db.get(OrganizationMembership, membership_id)
    if not item:
        raise HTTPException(404, "Membership not found")
    previous = item.role
    item.role, item.status = payload.role, "active"
    record(db, admin, "governance.membership_role_changed", "membership", item.id, {"previous_role": previous.value, "role": payload.role.value, "organization_id": item.organization_id})
    db.commit()
    return envelope(message="Workspace role updated")


@router.delete("/memberships/{membership_id}")
def remove_membership(membership_id: str, admin: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    item = db.get(OrganizationMembership, membership_id)
    if not item:
        raise HTTPException(404, "Membership not found")
    if item.role == MembershipRole.OWNER:
        owners = db.scalar(select(func.count(OrganizationMembership.id)).where(OrganizationMembership.organization_id == item.organization_id, OrganizationMembership.role == MembershipRole.OWNER, OrganizationMembership.status == "active")) or 0
        if owners <= 1:
            raise HTTPException(409, "Assign another owner before removing the final workspace owner")
    item.status = "removed"
    record(db, admin, "governance.membership_removed", "membership", item.id, {"organization_id": item.organization_id, "user_id": item.user_id})
    db.commit()
    return envelope(message="Workspace access removed")


@router.patch("/organizations/{organization_id}/status")
def change_organization_status(organization_id: str, payload: OrganizationStateChange, admin: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    organization = db.get(Organization, organization_id)
    if not organization:
        raise HTTPException(404, "Organization not found")
    if payload.status not in {"active", "suspended"} or payload.confirmation != organization.name:
        raise HTTPException(422, "A valid status and exact organization name confirmation are required")
    previous, organization.status = organization.status, payload.status
    record(db, admin, f"governance.organization_{payload.status}", "organization", organization.id, {"previous_status": previous})
    db.commit()
    return envelope({"status": organization.status}, "Organization status updated")


@router.patch("/organizations/{organization_id}/subscription")
def change_subscription(organization_id: str, payload: SubscriptionChange, admin: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    organization = db.get(Organization, organization_id)
    if not organization:
        raise HTTPException(404, "Organization not found")
    if payload.plan_key not in PLAN_CATALOG or payload.status not in {"trialing", "active", "past_due", "canceled"} or payload.confirmation != organization.name:
        raise HTTPException(422, "Valid subscription values and exact organization name confirmation are required")
    subscription = ensure_subscription(db, organization_id)
    previous = {"plan_key": subscription.plan_key, "status": subscription.status}
    subscription.plan_key, subscription.status = payload.plan_key, payload.status
    record(db, admin, "governance.subscription_changed", "organization", organization_id, {"previous": previous, "plan_key": payload.plan_key, "status": payload.status})
    db.commit()
    return envelope({"plan_key": subscription.plan_key, "status": subscription.status}, "Subscription updated")


def audit_statement(q: str, action: str, actor_id: str | None):
    statement = select(AuditLog).order_by(AuditLog.created_at.desc())
    if q:
        statement = statement.where(or_(AuditLog.action.ilike(f"%{q}%"), AuditLog.target_type.ilike(f"%{q}%"), AuditLog.target_id.ilike(f"%{q}%")))
    if action:
        statement = statement.where(AuditLog.action.ilike(f"%{action}%"))
    if actor_id:
        statement = statement.where(AuditLog.actor_id == actor_id)
    return statement


@router.get("/audit")
def audit_logs(q: str = "", action: str = "", actor_id: str | None = None, limit: int = Query(100, ge=1, le=500), _admin: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    items = db.scalars(audit_statement(q, action, actor_id).limit(limit)).all()
    return envelope([{"id": item.id, "actor_id": item.actor_id, "action": item.action, "target_type": item.target_type, "target_id": item.target_id, "metadata": item.metadata_json, "created_at": item.created_at.isoformat()} for item in items])


@router.get("/audit/export")
def export_audit(q: str = "", action: str = "", actor_id: str | None = None, admin: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    items = db.scalars(audit_statement(q, action, actor_id).limit(5000)).all()
    output = io.StringIO(); writer = csv.writer(output); writer.writerow(["timestamp", "actor_id", "action", "target_type", "target_id", "metadata"])
    for item in items:
        writer.writerow([item.created_at.isoformat(), item.actor_id or "", item.action, item.target_type or "", item.target_id or "", str(item.metadata_json or {})])
    record(db, admin, "governance.audit_exported", "audit_log", admin.id, {"records": len(items)}); db.commit()
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=smarthire-audit-log.csv"})
