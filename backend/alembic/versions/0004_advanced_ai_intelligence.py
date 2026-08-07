"""Advanced AI intelligence, evidence, scorecards, and override history."""

from alembic import op
import sqlalchemy as sa

revision = "0004_advanced_ai_intelligence"
down_revision = "0003_dual_engine_scoring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001 creates the schema from the current models, so on a fresh database
    # these columns already exist. Guard each one, as 0002 does.
    inspector = sa.inspect(op.get_bind())

    def add_missing(table: str, columns: list[sa.Column]) -> None:
        existing = {column["name"] for column in inspector.get_columns(table)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column)

    add_missing(
        "jobs",
        [
            sa.Column("scorecard", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("skill_priorities", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("domain_keywords", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("education_requirements", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("certification_requirements", sa.JSON(), nullable=False, server_default="[]"),
        ],
    )
    add_missing(
        "applications",
        [
            sa.Column("structured_profile", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("evidence_matrix", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("analysis_version", sa.String(length=40), nullable=False, server_default="advanced-v1"),
            sa.Column("parser_version", sa.String(length=40), nullable=True),
            sa.Column("override_score", sa.Float(), nullable=True),
            sa.Column("override_reason", sa.Text(), nullable=True),
            sa.Column("overridden_by_id", sa.String(length=36), nullable=True),
            sa.Column("overridden_at", sa.DateTime(timezone=True), nullable=True),
        ],
    )

    # Match on the constrained column, not the constraint name: create_all names
    # this FK applications_overridden_by_id_fkey, so a name check would miss it
    # and Postgres would happily create a second, redundant constraint.
    existing_fk_columns = {
        tuple(fk["constrained_columns"]) for fk in inspector.get_foreign_keys("applications")
    }
    if ("overridden_by_id",) not in existing_fk_columns:
        op.create_foreign_key(
            "fk_applications_overridden_by", "applications", "users", ["overridden_by_id"], ["id"]
        )

    if "score_overrides" not in inspector.get_table_names():
        op.create_table(
            "score_overrides",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("application_id", sa.String(length=36), nullable=False),
            sa.Column("actor_id", sa.String(length=36), nullable=False),
            sa.Column("previous_score", sa.Float(), nullable=True),
            sa.Column("override_score", sa.Float(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["application_id"], ["applications.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_score_overrides_actor_id", "score_overrides", ["actor_id"])
        op.create_index("ix_score_overrides_application_id", "score_overrides", ["application_id"])


def downgrade() -> None:
    op.drop_index("ix_score_overrides_application_id", table_name="score_overrides")
    op.drop_index("ix_score_overrides_actor_id", table_name="score_overrides")
    op.drop_table("score_overrides")
    op.drop_constraint("fk_applications_overridden_by", "applications", type_="foreignkey")
    for column in ("overridden_at", "overridden_by_id", "override_reason", "override_score", "parser_version", "analysis_version", "evidence_matrix", "structured_profile"):
        op.drop_column("applications", column)
    for column in ("certification_requirements", "education_requirements", "domain_keywords", "skill_priorities", "scorecard"):
        op.drop_column("jobs", column)
