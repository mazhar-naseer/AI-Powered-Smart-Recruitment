"""Market-ready ATS tenancy, collaboration, pipeline, jobs, and notifications."""

import re
import uuid
from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa

revision = "0006_market_ats_foundation"
down_revision = "0005_advanced_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("organizations", sa.Column("id",sa.String(36),primary_key=True),sa.Column("name",sa.String(160),nullable=False),sa.Column("slug",sa.String(180),nullable=False,unique=True),sa.Column("status",sa.String(24),nullable=False),sa.Column("settings_json",sa.JSON(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False))
    op.create_index("ix_organizations_name","organizations",["name"]);op.create_index("ix_organizations_slug","organizations",["slug"],unique=True);op.create_index("ix_organizations_status","organizations",["status"])
    op.add_column("users",sa.Column("active_organization_id",sa.String(36),sa.ForeignKey("organizations.id")));op.create_index("ix_users_active_organization_id","users",["active_organization_id"])
    op.create_table("organization_memberships",sa.Column("id",sa.String(36),primary_key=True),sa.Column("organization_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),sa.Column("user_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),sa.Column("role",sa.String(20),nullable=False),sa.Column("status",sa.String(24),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("organization_id","user_id",name="uq_membership_organization_user"))
    for column in ("organization_id","user_id","role","status"):op.create_index(f"ix_organization_memberships_{column}","organization_memberships",[column])
    op.create_table("organization_invitations",sa.Column("id",sa.String(36),primary_key=True),sa.Column("organization_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),sa.Column("email",sa.String(320),nullable=False),sa.Column("role",sa.String(20),nullable=False),sa.Column("token_hash",sa.String(64),nullable=False,unique=True),sa.Column("invited_by_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),sa.Column("accepted_at",sa.DateTime(timezone=True)),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False))
    for column in ("organization_id","email","token_hash"):op.create_index(f"ix_organization_invitations_{column}","organization_invitations",[column],unique=column=="token_hash")
    op.create_table("pipeline_stages",sa.Column("id",sa.String(36),primary_key=True),sa.Column("organization_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),sa.Column("name",sa.String(80),nullable=False),sa.Column("color",sa.String(20),nullable=False),sa.Column("position",sa.Integer(),nullable=False),sa.Column("category",sa.String(30),nullable=False),sa.Column("is_default",sa.Boolean(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("organization_id","name",name="uq_pipeline_stage_name"));op.create_index("ix_pipeline_stages_organization_id","pipeline_stages",["organization_id"])
    op.add_column("jobs",sa.Column("organization_id",sa.String(36),sa.ForeignKey("organizations.id")));op.create_index("ix_jobs_organization_id","jobs",["organization_id"])
    op.add_column("applications",sa.Column("organization_id",sa.String(36),sa.ForeignKey("organizations.id")));op.add_column("applications",sa.Column("stage_id",sa.String(36),sa.ForeignKey("pipeline_stages.id")));op.add_column("applications",sa.Column("assigned_to_id",sa.String(36),sa.ForeignKey("users.id")));op.add_column("applications",sa.Column("candidate_tags",sa.JSON(),nullable=False,server_default="[]"))
    for column in ("organization_id","stage_id","assigned_to_id"):op.create_index(f"ix_applications_{column}","applications",[column])
    op.create_table("candidate_notes",sa.Column("id",sa.String(36),primary_key=True),sa.Column("organization_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),sa.Column("application_id",sa.String(36),sa.ForeignKey("applications.id"),nullable=False),sa.Column("author_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),sa.Column("body",sa.Text(),nullable=False),sa.Column("visibility",sa.String(20),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False))
    op.create_table("candidate_timeline",sa.Column("id",sa.String(36),primary_key=True),sa.Column("organization_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),sa.Column("application_id",sa.String(36),sa.ForeignKey("applications.id"),nullable=False),sa.Column("actor_id",sa.String(36),sa.ForeignKey("users.id")),sa.Column("event_type",sa.String(80),nullable=False),sa.Column("description",sa.String(500),nullable=False),sa.Column("metadata_json",sa.JSON(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_table("notifications",sa.Column("id",sa.String(36),primary_key=True),sa.Column("user_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),sa.Column("organization_id",sa.String(36),sa.ForeignKey("organizations.id")),sa.Column("type",sa.String(60),nullable=False),sa.Column("title",sa.String(180),nullable=False),sa.Column("message",sa.String(500),nullable=False),sa.Column("action_url",sa.String(500)),sa.Column("read_at",sa.DateTime(timezone=True)),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_table("background_jobs",sa.Column("id",sa.String(36),primary_key=True),sa.Column("organization_id",sa.String(36),sa.ForeignKey("organizations.id")),sa.Column("job_type",sa.String(80),nullable=False),sa.Column("payload",sa.JSON(),nullable=False),sa.Column("status",sa.String(20),nullable=False),sa.Column("attempts",sa.Integer(),nullable=False),sa.Column("max_attempts",sa.Integer(),nullable=False),sa.Column("run_after",sa.DateTime(timezone=True),nullable=False),sa.Column("locked_at",sa.DateTime(timezone=True)),sa.Column("completed_at",sa.DateTime(timezone=True)),sa.Column("last_error",sa.String(1000)),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    for table, columns in {"candidate_notes":["organization_id","application_id","author_id"],"candidate_timeline":["organization_id","application_id","actor_id","event_type","created_at"],"notifications":["user_id","organization_id","type","read_at","created_at"],"background_jobs":["organization_id","job_type","status","run_after"]}.items():
        for column in columns:op.create_index(f"ix_{table}_{column}",table,[column])

    bind=op.get_bind();now=datetime.now(UTC);employers=bind.execute(sa.text("SELECT id, full_name, company_name FROM users WHERE role = 'EMPLOYER'")).mappings().all()
    defaults=[("Applied","#3157d5","active",True),("Screening","#7c55d9","active",False),("Interview","#d58a20","active",False),("Offer","#15956c","active",False),("Hired","#087848","hired",False),("Rejected","#ca3f4c","rejected",False)]
    for employer in employers:
        org_id=str(uuid.uuid4());name=employer["company_name"] or f'{employer["full_name"]} Company';slug=re.sub(r"[^a-z0-9]+","-",name.lower()).strip("-")+f"-{uuid.uuid4().hex[:8]}"
        bind.execute(sa.text("INSERT INTO organizations (id,name,slug,status,settings_json,created_at,updated_at) VALUES (:id,:name,:slug,'active',:settings,:now,:now)"),{"id":org_id,"name":name,"slug":slug,"settings":"{}","now":now})
        bind.execute(sa.text("INSERT INTO organization_memberships (id,organization_id,user_id,role,status,created_at,updated_at) VALUES (:id,:org,:user,'owner','active',:now,:now)"),{"id":str(uuid.uuid4()),"org":org_id,"user":employer["id"],"now":now})
        bind.execute(sa.text("UPDATE users SET active_organization_id=:org WHERE id=:user"),{"org":org_id,"user":employer["id"]})
        applied_stage=None
        for position,(stage_name,color,category,is_default) in enumerate(defaults):
            stage_id=str(uuid.uuid4());applied_stage=stage_id if is_default else applied_stage
            bind.execute(sa.text("INSERT INTO pipeline_stages (id,organization_id,name,color,position,category,is_default,created_at,updated_at) VALUES (:id,:org,:name,:color,:position,:category,:default,:now,:now)"),{"id":stage_id,"org":org_id,"name":stage_name,"color":color,"position":position,"category":category,"default":is_default,"now":now})
        bind.execute(sa.text("UPDATE jobs SET organization_id=:org WHERE employer_id=:user"),{"org":org_id,"user":employer["id"]})
        bind.execute(sa.text("UPDATE applications SET organization_id=:org, stage_id=:stage WHERE job_id IN (SELECT id FROM jobs WHERE organization_id=:org)"),{"org":org_id,"stage":applied_stage})


def downgrade() -> None:
    for column in ("assigned_to_id","stage_id","organization_id"):op.drop_index(f"ix_applications_{column}",table_name="applications")
    for column in ("candidate_tags","assigned_to_id","stage_id","organization_id"):op.drop_column("applications",column)
    op.drop_index("ix_jobs_organization_id",table_name="jobs");op.drop_column("jobs","organization_id")
    op.drop_index("ix_users_active_organization_id",table_name="users");op.drop_column("users","active_organization_id")
    for table in ("background_jobs","notifications","candidate_timeline","candidate_notes","organization_invitations","organization_memberships","pipeline_stages","organizations"):op.drop_table(table)
