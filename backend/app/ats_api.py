import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import (
    Application, AuditLog, BackgroundJob, CandidateNote, CandidateTimeline, Job,
    MembershipRole, Notification, Organization, OrganizationInvitation, OrganizationMembership,
    PipelineStage, Role, User,
)
from app.schemas import (
    CandidateAssignRequest, CandidateMoveRequest, CandidateNoteRequest,
    CandidateTagsRequest, MembershipRoleUpdate, StageCreate, StageUpdate,
    TeamInviteRequest, UserOut, NotificationPreferencesUpdate,
    WorkspaceSwitchRequest,
)
from app.security import current_user, require_roles
from app.tenancy import ensure_membership, membership_for, permissions_for, require_permission
from app.email_service import send_team_invitation
from app.config import get_settings
from app.saas import enforce_limit
from app.notification_service import create_notification, preferences_for
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1")
settings = get_settings()


def envelope(data=None, message="Success"):
    return {"success": True, "message": message, "data": data}


def timeline(db: Session, organization_id: str, application_id: str, actor_id: str | None, event_type: str, description: str, metadata: dict | None = None):
    db.add(CandidateTimeline(organization_id=organization_id, application_id=application_id, actor_id=actor_id, event_type=event_type, description=description, metadata_json=metadata or {}))


def notify(db: Session, user_id: str, organization_id: str | None, type_: str, title: str, message: str, action_url: str | None = None, email_category: str | None = None):
    create_notification(db, user_id=user_id, organization_id=organization_id, type_=type_, title=title, message=message, action_url=action_url, email_category=email_category)


def application_for_team(db: Session, user: User, application_id: str, permission="candidates.manage") -> tuple[Application, OrganizationMembership]:
    application = db.scalar(select(Application).options(joinedload(Application.applicant), joinedload(Application.job)).where(Application.id == application_id))
    if not application or not application.organization_id:
        raise HTTPException(404, "Candidate application not found")
    membership = require_permission(db, user, permission, application.organization_id)
    return application, membership


@router.get("/workspace")
def workspace(user: User = Depends(require_roles(Role.EMPLOYER)), db: Session = Depends(get_db)):
    membership = ensure_membership(db, user)
    db.commit()
    return envelope({"organization": {"id": membership.organization.id, "name": membership.organization.name, "slug": membership.organization.slug, "status": membership.organization.status}, "membership": {"id": membership.id, "role": membership.role.value, "permissions": permissions_for(membership)}})


@router.get("/workspaces")
def workspaces(user: User = Depends(require_roles(Role.EMPLOYER)), db: Session = Depends(get_db)):
    memberships = db.scalars(select(OrganizationMembership).options(joinedload(OrganizationMembership.organization)).where(OrganizationMembership.user_id == user.id, OrganizationMembership.status == "active").order_by(OrganizationMembership.created_at)).all()
    if not memberships:
        memberships = [ensure_membership(db, user)];db.commit()
    return envelope([{"organization":{"id":item.organization.id,"name":item.organization.name,"slug":item.organization.slug},"role":item.role.value,"active":item.organization_id==user.active_organization_id} for item in memberships])


@router.post("/workspace/switch")
def switch_workspace(payload: WorkspaceSwitchRequest, user: User = Depends(require_roles(Role.EMPLOYER)), db: Session = Depends(get_db)):
    membership = membership_for(db, user, payload.organization_id)
    if not membership:raise HTTPException(404,"Workspace membership not found")
    user.active_organization_id=membership.organization_id;db.add(AuditLog(actor_id=user.id,action="workspace.switched",target_type="organization",target_id=membership.organization_id));db.commit();return envelope({"organization_id":membership.organization_id},"Active workspace changed")


@router.get("/workspace/team")
def team(user: User = Depends(require_roles(Role.EMPLOYER)), db: Session = Depends(get_db)):
    membership = ensure_membership(db, user)
    members = db.scalars(select(OrganizationMembership).options(joinedload(OrganizationMembership.user)).where(OrganizationMembership.organization_id == membership.organization_id, OrganizationMembership.status == "active").order_by(OrganizationMembership.created_at)).all()
    invitations = db.scalars(select(OrganizationInvitation).where(OrganizationInvitation.organization_id == membership.organization_id, OrganizationInvitation.accepted_at.is_(None), OrganizationInvitation.expires_at > datetime.now(UTC))).all()
    return envelope({"members": [{"id": item.id, "role": item.role.value, "status": item.status, "joined_at": item.created_at.isoformat(), "user": UserOut.model_validate(item.user).model_dump(mode="json")} for item in members], "invitations": [{"id": item.id, "email": item.email, "role": item.role.value, "expires_at": item.expires_at.isoformat()} for item in invitations], "current_role": membership.role.value})


@router.post("/workspace/team/invitations", status_code=201)
def invite_member(payload: TeamInviteRequest, user: User = Depends(require_roles(Role.EMPLOYER)), db: Session = Depends(get_db)):
    membership = ensure_membership(db, user)
    require_permission(db, user, "team.manage", membership.organization_id)
    enforce_limit(db, membership.organization_id, "team_members")
    email = str(payload.email).lower().strip()
    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user and existing_user.role != Role.EMPLOYER:
        raise HTTPException(409, "This email belongs to a non-recruiter account")
    if existing_user and membership_for(db, existing_user, membership.organization_id):
        raise HTTPException(409, "This user is already a workspace member")
    raw_token = secrets.token_urlsafe(32)
    invitation = OrganizationInvitation(organization_id=membership.organization_id, email=email, role=MembershipRole(payload.role), token_hash=hashlib.sha256(raw_token.encode()).hexdigest(), invited_by_id=user.id, expires_at=datetime.now(UTC) + timedelta(days=7))
    db.add(invitation)
    send_team_invitation(email, user.full_name, membership.organization.name, payload.role, raw_token)
    if existing_user:
        notify(db, existing_user.id, membership.organization_id, "team_invitation", f"Invitation to {membership.organization.name}", f"{user.full_name} invited you to join as {payload.role}.", f"/team/invitations/{raw_token}")
    db.add(AuditLog(actor_id=user.id, action="team.invitation_created", target_type="organization", target_id=membership.organization_id, metadata_json={"email": email, "role": payload.role}))
    db.commit()
    data={"id":invitation.id,"email":email,"role":payload.role}
    if settings.environment=="development":data["invitation_token"]=raw_token
    return envelope(data, "Recruiter invitation created")


@router.post("/workspace/team/invitations/{token}/accept")
def accept_invitation(token: str, user: User = Depends(require_roles(Role.EMPLOYER)), db: Session = Depends(get_db)):
    invitation = db.scalar(select(OrganizationInvitation).where(OrganizationInvitation.token_hash == hashlib.sha256(token.encode()).hexdigest(), OrganizationInvitation.accepted_at.is_(None), OrganizationInvitation.expires_at > datetime.now(UTC)))
    if not invitation or invitation.email != user.email.lower():
        raise HTTPException(400, "Invitation is invalid, expired, or belongs to another email")
    existing = membership_for(db, user, invitation.organization_id)
    if not existing:
        db.add(OrganizationMembership(organization_id=invitation.organization_id, user_id=user.id, role=invitation.role))
    invitation.accepted_at = datetime.now(UTC)
    user.active_organization_id = invitation.organization_id
    db.add(AuditLog(actor_id=user.id, action="team.invitation_accepted", target_type="organization", target_id=invitation.organization_id))
    db.commit()
    return envelope(message="Workspace invitation accepted")


@router.patch("/workspace/team/{membership_id}")
def change_member_role(membership_id: str, payload: MembershipRoleUpdate, user: User = Depends(require_roles(Role.EMPLOYER)), db: Session = Depends(get_db)):
    current = ensure_membership(db, user);require_permission(db, user, "team.manage", current.organization_id)
    target = db.get(OrganizationMembership, membership_id)
    if not target or target.organization_id != current.organization_id or target.role == MembershipRole.OWNER:
        raise HTTPException(404, "Team member not found or protected")
    target.role = MembershipRole(payload.role)
    db.add(AuditLog(actor_id=user.id, action="team.role_changed", target_type="membership", target_id=target.id, metadata_json={"role": payload.role}))
    db.commit();return envelope(message="Team role updated")


@router.delete("/workspace/team/{membership_id}")
def remove_member(membership_id: str, user: User = Depends(require_roles(Role.EMPLOYER)), db: Session = Depends(get_db)):
    current = ensure_membership(db, user);require_permission(db, user, "team.manage", current.organization_id)
    target = db.get(OrganizationMembership, membership_id)
    if not target or target.organization_id != current.organization_id or target.role == MembershipRole.OWNER:
        raise HTTPException(404, "Team member not found or protected")
    target.status = "removed";db.add(AuditLog(actor_id=user.id, action="team.member_removed", target_type="membership", target_id=target.id));db.commit();return envelope(message="Team member removed")


@router.delete("/workspace/team/invitations/{invitation_id}")
def revoke_invitation(invitation_id:str,user:User=Depends(require_roles(Role.EMPLOYER)),db:Session=Depends(get_db)):
    current=ensure_membership(db,user);require_permission(db,user,"team.manage",current.organization_id);invitation=db.get(OrganizationInvitation,invitation_id)
    if not invitation or invitation.organization_id!=current.organization_id or invitation.accepted_at:raise HTTPException(404,"Pending invitation not found")
    db.delete(invitation);db.add(AuditLog(actor_id=user.id,action="team.invitation_revoked",target_type="organization",target_id=current.organization_id));db.commit();return envelope(message="Invitation revoked")


@router.get("/workspace/pipeline/stages")
def stages(user: User = Depends(require_roles(Role.EMPLOYER)), db: Session = Depends(get_db)):
    membership = ensure_membership(db, user)
    items = db.scalars(select(PipelineStage).where(PipelineStage.organization_id == membership.organization_id).order_by(PipelineStage.position)).all()
    return envelope([{"id": item.id, "name": item.name, "color": item.color, "position": item.position, "category": item.category, "is_default": item.is_default} for item in items])


@router.post("/workspace/pipeline/stages", status_code=201)
def create_stage(payload: StageCreate, user: User = Depends(require_roles(Role.EMPLOYER)), db: Session = Depends(get_db)):
    membership = ensure_membership(db, user);require_permission(db, user, "organization.manage", membership.organization_id)
    position = db.scalar(select(func.count(PipelineStage.id)).where(PipelineStage.organization_id == membership.organization_id)) or 0
    stage = PipelineStage(organization_id=membership.organization_id, position=position, **payload.model_dump());db.add(stage);db.commit();db.refresh(stage);return envelope({"id": stage.id, **payload.model_dump(), "position": position}, "Pipeline stage created")


@router.patch("/workspace/pipeline/stages/{stage_id}")
def update_stage(stage_id: str, payload: StageUpdate, user: User = Depends(require_roles(Role.EMPLOYER)), db: Session = Depends(get_db)):
    membership=ensure_membership(db,user);require_permission(db,user,"organization.manage",membership.organization_id);stage=db.get(PipelineStage,stage_id)
    if not stage or stage.organization_id!=membership.organization_id:raise HTTPException(404,"Pipeline stage not found")
    for key,value in payload.model_dump(exclude_unset=True).items():setattr(stage,key,value)
    db.commit();return envelope(message="Pipeline stage updated")


@router.delete("/workspace/pipeline/stages/{stage_id}")
def delete_stage(stage_id:str,user:User=Depends(require_roles(Role.EMPLOYER)),db:Session=Depends(get_db)):
    membership=ensure_membership(db,user);require_permission(db,user,"organization.manage",membership.organization_id);stage=db.get(PipelineStage,stage_id)
    if not stage or stage.organization_id!=membership.organization_id or stage.is_default:raise HTTPException(404,"Pipeline stage not found or protected")
    if db.scalar(select(func.count(Application.id)).where(Application.stage_id==stage.id)):raise HTTPException(409,"Move candidates out of this stage before deleting it")
    db.delete(stage);db.commit();return envelope(message="Pipeline stage deleted")


@router.get("/workspace/candidates")
def candidates(job_id: str | None = None, stage_id: str | None = None, q: str = "", user: User = Depends(require_roles(Role.EMPLOYER)), db: Session = Depends(get_db)):
    membership=ensure_membership(db,user);require_permission(db,user,"analytics.view",membership.organization_id)
    stmt=select(Application).options(joinedload(Application.applicant),joinedload(Application.job)).where(Application.organization_id==membership.organization_id)
    if job_id:stmt=stmt.where(Application.job_id==job_id)
    if stage_id:stmt=stmt.where(Application.stage_id==stage_id)
    if q:stmt=stmt.where(Application.applicant.has(User.full_name.ilike(f"%{q}%")))
    items=db.scalars(stmt.order_by(Application.updated_at.desc())).unique().all()
    return envelope([{"id":a.id,"job_id":a.job_id,"stage_id":a.stage_id,"assigned_to_id":a.assigned_to_id,"tags":a.candidate_tags or [],"final_score":a.final_score,"override_score":a.override_score,"analysis_status":a.status.value,"created_at":a.created_at.isoformat(),"updated_at":a.updated_at.isoformat(),"applicant":UserOut.model_validate(a.applicant).model_dump(mode="json"),"job":{"id":a.job.id,"title":a.job.title}} for a in items])


@router.patch("/workspace/candidates/{application_id}/stage")
def move_candidate(application_id: str,payload:CandidateMoveRequest,user:User=Depends(require_roles(Role.EMPLOYER)),db:Session=Depends(get_db)):
    application,membership=application_for_team(db,user,application_id);stage=db.get(PipelineStage,payload.stage_id)
    if not stage or stage.organization_id!=membership.organization_id:raise HTTPException(404,"Pipeline stage not found")
    previous=application.stage_id;application.stage_id=stage.id;timeline(db,membership.organization_id,application.id,user.id,"stage_changed",f"{user.full_name} moved the candidate to {stage.name}.",{"previous_stage_id":previous,"stage_id":stage.id})
    category = "interviews_offers" if any(term in f"{stage.name} {stage.category}".lower() for term in ("interview", "offer", "hired")) else "application_status_changes"
    notify(db,application.applicant_id,membership.organization_id,"application_stage",f"Application moved to {stage.name}",f"Your application for {application.job.title} has progressed.",f"/applicant/applications?application={application.id}",category)
    db.commit();return envelope({"stage_id":stage.id},"Candidate stage updated")


@router.patch("/workspace/candidates/{application_id}/assignment")
def assign_candidate(application_id:str,payload:CandidateAssignRequest,user:User=Depends(require_roles(Role.EMPLOYER)),db:Session=Depends(get_db)):
    application,membership=application_for_team(db,user,application_id)
    if payload.user_id:
        assignee=db.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id==membership.organization_id,OrganizationMembership.user_id==payload.user_id,OrganizationMembership.status=="active"))
        if not assignee:raise HTTPException(422,"Assignee must be an active workspace member")
    application.assigned_to_id=payload.user_id;timeline(db,membership.organization_id,application.id,user.id,"assignment_changed",f"{user.full_name} updated candidate ownership.",{"assigned_to_id":payload.user_id})
    if payload.user_id:notify(db,payload.user_id,membership.organization_id,"candidate_assigned","Candidate assigned to you",f"You are now responsible for {application.applicant.full_name}.",f"/employer/candidates/{application.id}","assignments")
    db.commit();return envelope({"assigned_to_id":payload.user_id},"Candidate assignment updated")


@router.patch("/workspace/candidates/{application_id}/tags")
def update_tags(application_id:str,payload:CandidateTagsRequest,user:User=Depends(require_roles(Role.EMPLOYER)),db:Session=Depends(get_db)):
    application,membership=application_for_team(db,user,application_id);application.candidate_tags=payload.tags;timeline(db,membership.organization_id,application.id,user.id,"tags_updated",f"{user.full_name} updated candidate tags.",{"tags":payload.tags});db.commit();return envelope({"tags":payload.tags},"Candidate tags updated")


@router.get("/workspace/candidates/{application_id}/collaboration")
def candidate_collaboration(application_id:str,user:User=Depends(require_roles(Role.EMPLOYER)),db:Session=Depends(get_db)):
    application,membership=application_for_team(db,user,application_id,"analytics.view")
    notes=db.scalars(select(CandidateNote).options(joinedload(CandidateNote.author)).where(CandidateNote.application_id==application.id).order_by(CandidateNote.created_at.desc())).all()
    events=db.scalars(select(CandidateTimeline).where(CandidateTimeline.application_id==application.id).order_by(CandidateTimeline.created_at.desc()).limit(100)).all()
    return envelope({"notes":[{"id":n.id,"body":n.body,"created_at":n.created_at.isoformat(),"author":{"id":n.author.id,"full_name":n.author.full_name}} for n in notes],"timeline":[{"id":e.id,"event_type":e.event_type,"description":e.description,"metadata":e.metadata_json,"actor_id":e.actor_id,"created_at":e.created_at.isoformat()} for e in events]})


@router.post("/workspace/candidates/{application_id}/notes",status_code=201)
def add_note(application_id:str,payload:CandidateNoteRequest,user:User=Depends(require_roles(Role.EMPLOYER)),db:Session=Depends(get_db)):
    application,membership=application_for_team(db,user,application_id,"candidates.comment");note=CandidateNote(organization_id=membership.organization_id,application_id=application.id,author_id=user.id,body=payload.body.strip());db.add(note);timeline(db,membership.organization_id,application.id,user.id,"note_added",f"{user.full_name} added an internal note.");db.commit();db.refresh(note);return envelope({"id":note.id,"body":note.body,"created_at":note.created_at.isoformat(),"author":{"id":user.id,"full_name":user.full_name}},"Internal note added")


@router.get("/notifications")
def notifications(unread_only:bool=False,user:User=Depends(current_user),db:Session=Depends(get_db)):
    stmt=select(Notification).where(Notification.user_id==user.id)
    if unread_only:stmt=stmt.where(Notification.read_at.is_(None))
    items=db.scalars(stmt.order_by(Notification.created_at.desc()).limit(100)).all();unread=db.scalar(select(func.count(Notification.id)).where(Notification.user_id==user.id,Notification.read_at.is_(None))) or 0
    return envelope({"unread_count":unread,"items":[{"id":n.id,"type":n.type,"title":n.title,"message":n.message,"action_url":n.action_url,"read_at":n.read_at.isoformat() if n.read_at else None,"created_at":n.created_at.isoformat()} for n in items]})


@router.get("/notifications/preferences")
def notification_preferences(user: User = Depends(current_user)):
    return envelope(preferences_for(user))


@router.patch("/notifications/preferences")
def update_notification_preferences(payload: NotificationPreferencesUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    values = preferences_for(user)
    values.update(payload.model_dump(exclude_none=True))
    user.notification_preferences = values
    db.commit()
    return envelope(values, "Email notification preferences updated")


@router.patch("/notifications/{notification_id}/read")
def read_notification(notification_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    item=db.get(Notification,notification_id)
    if not item or item.user_id!=user.id:raise HTTPException(404,"Notification not found")
    item.read_at=datetime.now(UTC);db.commit();return envelope(message="Notification marked as read")


@router.post("/notifications/read-all")
def read_all_notifications(user:User=Depends(current_user),db:Session=Depends(get_db)):
    for item in db.scalars(select(Notification).where(Notification.user_id==user.id,Notification.read_at.is_(None))).all():item.read_at=datetime.now(UTC)
    db.commit();return envelope(message="All notifications marked as read")


@router.get("/workspace/operations")
def operations(user:User=Depends(require_roles(Role.EMPLOYER)),db:Session=Depends(get_db)):
    membership=ensure_membership(db,user);require_permission(db,user,"analytics.view",membership.organization_id)
    jobs=db.scalar(select(func.count(Job.id)).where(Job.organization_id==membership.organization_id)) or 0;applications=db.scalar(select(func.count(Application.id)).where(Application.organization_id==membership.organization_id)) or 0;queued=db.scalar(select(func.count(BackgroundJob.id)).where(BackgroundJob.organization_id==membership.organization_id,BackgroundJob.status.in_(["queued","running"]))) or 0
    audits=db.scalars(select(AuditLog).where(AuditLog.metadata_json["organization_id"].as_string()==membership.organization_id).order_by(AuditLog.created_at.desc()).limit(25)).all()
    return envelope({"jobs":jobs,"applications":applications,"background_jobs_active":queued,"recent_audit":[{"id":a.id,"action":a.action,"actor_id":a.actor_id,"target_type":a.target_type,"target_id":a.target_id,"metadata":a.metadata_json,"created_at":a.created_at.isoformat()} for a in audits]})


@router.get("/admin/operations/monitoring")
def admin_operations(user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    organizations=db.scalar(select(func.count()).select_from(Organization)) or 0
    memberships=db.scalar(select(func.count(OrganizationMembership.id)).where(OrganizationMembership.status=="active")) or 0
    queue={status:db.scalar(select(func.count(BackgroundJob.id)).where(BackgroundJob.status==status)) or 0 for status in ("queued","running","completed","failed")}
    recent=db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(50)).all()
    return envelope({"organizations":organizations,"active_memberships":memberships,"background_jobs":queue,"recent_audit":[{"id":item.id,"action":item.action,"actor_id":item.actor_id,"target_type":item.target_type,"target_id":item.target_id,"metadata":item.metadata_json,"created_at":item.created_at.isoformat()} for item in recent]})


@router.get("/admin/operations/background-jobs")
def admin_background_jobs(status: str | None = Query(default=None), user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    statement = select(BackgroundJob).order_by(BackgroundJob.created_at.desc()).limit(200)
    if status:
        if status not in {"queued", "running", "completed", "failed"}:
            raise HTTPException(422, "Unsupported background job status")
        statement = statement.where(BackgroundJob.status == status)
    jobs = db.scalars(statement).all()
    application_ids = [item.payload.get("application_id") for item in jobs if item.job_type == "application_analysis" and item.payload.get("application_id")]
    applications = db.scalars(
        select(Application)
        .options(joinedload(Application.applicant), joinedload(Application.job).joinedload(Job.organization))
        .where(Application.id.in_(application_ids))
    ).unique().all() if application_ids else []
    application_map = {item.id: item for item in applications}
    return envelope([{
        "id": item.id,
        "organization_id": item.organization_id,
        "job_type": item.job_type,
        "status": item.status.value,
        "attempts": item.attempts,
        "max_attempts": item.max_attempts,
        "run_after": item.run_after.isoformat(),
        "last_error": item.last_error,
        "created_at": item.created_at.isoformat(),
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        "application": ({
            "id": application.id,
            "candidate_name": application.applicant.full_name,
            "candidate_email": application.applicant.email,
            "job_id": application.job_id,
            "job_title": application.job.title,
            "organization_name": application.job.organization.name if application.job.organization else (application.job.employer.company_name or application.job.employer.full_name),
            "application_status": application.status.value,
            "final_score": application.final_score,
            "ai_provider": application.ai_provider,
            "ai_status": application.ai_status,
        } if (application := application_map.get(item.payload.get("application_id"))) else None),
    } for item in jobs])


@router.post("/admin/operations/background-jobs/{background_job_id}/retry")
def retry_background_job(background_job_id: str, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    item = db.get(BackgroundJob, background_job_id)
    if not item:
        raise HTTPException(404, "Background job not found")
    if item.status.value not in {"failed", "completed"}:
        raise HTTPException(409, "Only failed or completed jobs can be queued again")
    item.status = "queued"
    item.attempts = 0
    item.run_after = datetime.now(UTC)
    item.locked_at = None
    item.completed_at = None
    item.last_error = None
    db.add(AuditLog(actor_id=user.id, action="background_job.retried", target_type="background_job", target_id=item.id, metadata_json={"organization_id": item.organization_id}))
    db.commit()
    return envelope({"id": item.id, "status": "queued"}, "Background job queued for retry")
