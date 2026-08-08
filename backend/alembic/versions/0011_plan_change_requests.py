"""add plan change approval requests

Revision ID: 0011_plan_change_requests
Revises: 0010_password_resets
"""
from alembic import op
import sqlalchemy as sa
revision="0011_plan_change_requests";down_revision="0010_password_resets";branch_labels=None;depends_on=None
def upgrade():
    op.create_table("plan_change_requests",sa.Column("id",sa.String(36),primary_key=True),sa.Column("organization_id",sa.String(36),sa.ForeignKey("organizations.id"),nullable=False),sa.Column("requested_by_id",sa.String(36),sa.ForeignKey("users.id"),nullable=False),sa.Column("requested_plan_key",sa.String(40),nullable=False),sa.Column("current_plan_key",sa.String(40),nullable=False),sa.Column("status",sa.String(24),nullable=False),sa.Column("reviewed_by_id",sa.String(36),sa.ForeignKey("users.id")),sa.Column("review_note",sa.String(1000)),sa.Column("reviewed_at",sa.DateTime(timezone=True)),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
def downgrade(): op.drop_table("plan_change_requests")
