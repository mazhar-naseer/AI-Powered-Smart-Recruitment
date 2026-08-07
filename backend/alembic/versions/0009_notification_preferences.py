"""notification email preferences

Revision ID: 0009_notification_preferences
Revises: 0008_google_oauth
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_notification_preferences"
down_revision = "0008_google_oauth"
branch_labels = None
depends_on = None


def upgrade():
    default = "json_build_object('new_applications', true, 'application_status_changes', true, 'assignments', true, 'interviews_offers', true, 'ai_analysis_updates', false, 'weekly_summary', false)"
    op.add_column("users", sa.Column("notification_preferences", sa.JSON(), nullable=False, server_default=sa.text(default)))


def downgrade():
    op.drop_column("users", "notification_preferences")
