"""Store separate deterministic and Gemini scoring state."""

from alembic import op
import sqlalchemy as sa

revision = "0003_dual_engine_scoring"
down_revision = "0002_ai_email_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("ai_score", sa.Float(), nullable=True))
    op.add_column("applications", sa.Column("ai_status", sa.String(length=24), nullable=False, server_default="pending"))
    op.add_column("applications", sa.Column("ai_error", sa.String(length=500), nullable=True))
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
    op.alter_column("applications", "ai_status", server_default=None)


def downgrade() -> None:
    op.drop_column("applications", "ai_error")
    op.drop_column("applications", "ai_status")
    op.drop_column("applications", "ai_score")
