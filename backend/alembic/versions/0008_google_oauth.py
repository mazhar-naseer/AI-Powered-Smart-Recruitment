"""Google OAuth identities and single-use authorization handoff."""

from alembic import op
import sqlalchemy as sa

revision = "0008_google_oauth"
down_revision = "0007_commercial_saas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("oauth_states"):
        op.create_table(
            "oauth_states",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("state_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("provider", sa.String(40), nullable=False),
            sa.Column("intent", sa.String(20), nullable=False),
            sa.Column("requested_role", sa.String(20), nullable=False),
            sa.Column("code_verifier", sa.String(180), nullable=False),
            sa.Column("return_to", sa.String(500), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        for column in ("state_hash", "provider", "expires_at"):
            op.create_index(f"ix_oauth_states_{column}", "oauth_states", [column], unique=column == "state_hash")
    if not inspector.has_table("social_identities"):
        op.create_table(
            "social_identities",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("provider", sa.String(40), nullable=False),
            sa.Column("provider_subject", sa.String(255), nullable=False),
            sa.Column("provider_email", sa.String(320), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("provider", "provider_subject", name="uq_social_provider_subject"),
            sa.UniqueConstraint("user_id", "provider", name="uq_social_user_provider"),
        )
        for column in ("user_id", "provider", "provider_email"):
            op.create_index(f"ix_social_identities_{column}", "social_identities", [column])
    if not inspector.has_table("oauth_login_codes"):
        op.create_table(
            "oauth_login_codes",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        for column in ("code_hash", "user_id", "expires_at"):
            op.create_index(f"ix_oauth_login_codes_{column}", "oauth_login_codes", [column], unique=column == "code_hash")


def downgrade() -> None:
    for table in ("oauth_login_codes", "social_identities", "oauth_states"):
        if sa.inspect(op.get_bind()).has_table(table):
            op.drop_table(table)
