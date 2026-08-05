"""Comprehensive role-aware professional profiles."""

from alembic import op
import sqlalchemy as sa

revision = "0005_advanced_profiles"
down_revision = "0004_advanced_ai_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = [
        sa.Column("avatar_path", sa.String(255)), sa.Column("phone", sa.String(40)),
        sa.Column("bio", sa.Text()), sa.Column("website", sa.String(500)),
        sa.Column("linkedin_url", sa.String(500)), sa.Column("github_url", sa.String(500)),
        sa.Column("skills", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("languages", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("education", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("years_experience", sa.Integer()), sa.Column("availability", sa.String(80)),
        sa.Column("preferred_work_mode", sa.String(40)), sa.Column("portfolio_url", sa.String(500)),
        sa.Column("notice_period", sa.String(80)), sa.Column("industry", sa.String(120)),
        sa.Column("company_website", sa.String(500)), sa.Column("company_size", sa.String(40)),
        sa.Column("company_description", sa.Text()), sa.Column("founded_year", sa.Integer()),
    ]
    for column in columns:
        op.add_column("users", column)


def downgrade() -> None:
    for name in ("founded_year", "company_description", "company_size", "company_website", "industry", "notice_period", "portfolio_url", "preferred_work_mode", "availability", "years_experience", "education", "languages", "skills", "github_url", "linkedin_url", "website", "bio", "phone", "avatar_path"):
        op.drop_column("users", name)
