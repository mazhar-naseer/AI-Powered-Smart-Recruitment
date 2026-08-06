"""Store separate deterministic and Gemini scoring state."""

from alembic import op
import sqlalchemy as sa

revision = "0003_dual_engine_scoring"
down_revision = "0002_ai_email_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001 builds the schema with Base.metadata.create_all against the *current*
    # models, so on a fresh database these columns already exist by the time
    # this revision runs. Guard each one, as 0002 does.
    inspector = sa.inspect(op.get_bind())
    existing = {column["name"] for column in inspector.get_columns("applications")}
    added = []

    if "ai_score" not in existing:
        op.add_column("applications", sa.Column("ai_score", sa.Float(), nullable=True))
        added.append("ai_score")
    if "ai_status" not in existing:
        op.add_column(
            "applications",
            sa.Column("ai_status", sa.String(length=24), nullable=False, server_default="pending"),
        )
        added.append("ai_status")
    if "ai_error" not in existing:
        op.add_column("applications", sa.Column("ai_error", sa.String(length=500), nullable=True))
        added.append("ai_error")

    # The backfill only makes sense for rows that predate these columns. When
    # nothing was added the table is already in its target shape, and rerunning
    # the UPDATE would clobber live values.
    if added:
        op.execute(
            """
            UPDATE applications
            SET ai_score = CASE
                    WHEN component_scores ->> 'gemini_semantic' IS NOT NULL
                    THEN (component_scores ->> 'gemini_semantic')::double precision
                    ELSE NULL
                END,
                ai_status = CASE
                    WHEN component_scores ->> 'gemini_semantic' IS NOT NULL THEN 'completed'
                    ELSE 'failed'
                END,
                ai_error = CASE
                    WHEN component_scores ->> 'gemini_semantic' IS NOT NULL THEN NULL
                    ELSE 'This result predates AI status tracking; retry Gemini analysis to enrich it.'
                END
            """
        )

    if "ai_status" in added:
        op.alter_column("applications", "ai_status", server_default=None)


def downgrade() -> None:
    op.drop_column("applications", "ai_error")
    op.drop_column("applications", "ai_status")
    op.drop_column("applications", "ai_score")
