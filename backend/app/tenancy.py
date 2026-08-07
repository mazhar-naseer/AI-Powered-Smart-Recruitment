import re
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MembershipRole, Organization, OrganizationMembership, PipelineStage, User
from app.saas import ensure_subscription
from app.logging_config import get_logger

logger = get_logger(__name__)

PERMISSIONS = {
    MembershipRole.OWNER: {"organization.manage", "team.manage", "jobs.manage", "candidates.manage", "candidates.comment", "analytics.view"},
    MembershipRole.ADMIN: {"team.manage", "jobs.manage", "candidates.manage", "candidates.comment", "analytics.view"},
    MembershipRole.RECRUITER: {"jobs.manage", "candidates.manage", "candidates.comment", "analytics.view"},
    MembershipRole.VIEWER: {"analytics.view"},
}
DEFAULT_STAGES = [
    ("Applied", "#3157d5", "active", True),
    ("Screening", "#7c55d9", "active", False),
    ("Interview", "#d58a20", "active", False),
    ("Offer", "#15956c", "active", False),
    ("Hired", "#087848", "hired", False),
    ("Rejected", "#ca3f4c", "rejected", False),
]


def _slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "company"
    return f"{base}-{uuid.uuid4().hex[:8]}"


def create_workspace(db: Session, owner: User, name: str | None = None) -> OrganizationMembership:
    organization = Organization(name=(name or owner.company_name or f"{owner.full_name}'s Company").strip(), slug=_slug(name or owner.company_name or owner.full_name))
    db.add(organization)
    db.flush()
    ensure_subscription(db, organization.id)
    membership = OrganizationMembership(organization_id=organization.id, user_id=owner.id, role=MembershipRole.OWNER)
    db.add(membership)
    owner.active_organization_id = organization.id
    for position, (stage_name, color, category, is_default) in enumerate(DEFAULT_STAGES):
        db.add(PipelineStage(organization_id=organization.id, name=stage_name, color=color, category=category, position=position, is_default=is_default))
    db.flush()
    return membership


def membership_for(db: Session, user: User, organization_id: str | None = None) -> OrganizationMembership | None:
    stmt = select(OrganizationMembership).join(Organization).where(OrganizationMembership.user_id == user.id, OrganizationMembership.status == "active", Organization.status == "active")
    selected = organization_id or user.active_organization_id
    if selected:
        stmt = stmt.where(OrganizationMembership.organization_id == selected)
    return db.scalar(stmt.order_by(OrganizationMembership.created_at))


def ensure_membership(db: Session, user: User) -> OrganizationMembership:
    membership = membership_for(db, user)
    if not membership:
        membership = create_workspace(db, user)
    return membership


def require_permission(db: Session, user: User, permission: str, organization_id: str | None = None) -> OrganizationMembership:
    membership = membership_for(db, user, organization_id)
    if not membership or permission not in PERMISSIONS[membership.role]:
        raise HTTPException(403, "You do not have permission to perform this workspace action")
    return membership


def permissions_for(membership: OrganizationMembership) -> list[str]:
    return sorted(PERMISSIONS[membership.role])
