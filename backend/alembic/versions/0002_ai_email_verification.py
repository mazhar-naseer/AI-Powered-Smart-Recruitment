"""Advanced matching insights and email verification."""
from alembic import op
import sqlalchemy as sa

revision = "0002_ai_email_verification"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "email_verified" not in user_columns:
        with op.batch_alter_table("users") as batch:
            batch.add_column(sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.true()))
            batch.create_index("ix_users_email_verified", ["email_verified"])
    application_columns = {column["name"] for column in inspector.get_columns("applications")}
    if "component_scores" not in application_columns:
        with op.batch_alter_table("applications") as batch:
            batch.add_column(sa.Column("component_scores", sa.JSON(), nullable=False, server_default="{}"))
            batch.add_column(sa.Column("ai_summary", sa.Text()))
            batch.add_column(sa.Column("ai_strengths", sa.JSON(), nullable=False, server_default="[]"))
            batch.add_column(sa.Column("ai_gaps", sa.JSON(), nullable=False, server_default="[]"))
            batch.add_column(sa.Column("ai_recommendation", sa.String(40)))
            batch.add_column(sa.Column("ai_provider", sa.String(80)))
    if "email_verifications" not in inspector.get_table_names():
        op.create_table(
            "email_verifications",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False),
            sa.Column("code_hash", sa.String(64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_email_verifications_user_id", "email_verifications", ["user_id"])
        op.create_index("ix_email_verifications_token_hash", "email_verifications", ["token_hash"], unique=True)
        op.create_index("ix_email_verifications_code_hash", "email_verifications", ["code_hash"])


def downgrade():
    op.drop_table("email_verifications")
    with op.batch_alter_table("applications") as batch:
        for name in ("ai_provider", "ai_recommendation", "ai_gaps", "ai_strengths", "ai_summary", "component_scores"):
            batch.drop_column(name)
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_email_verified")
        batch.drop_column("email_verified")
