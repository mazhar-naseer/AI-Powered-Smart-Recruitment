"""Commercial SaaS subscriptions, usage metering, and billing events."""

import uuid
from datetime import UTC, datetime, timedelta

from alembic import op
import sqlalchemy as sa

revision = "0007_commercial_saas"
down_revision = "0006_market_ats_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_subscriptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False, unique=True),
        sa.Column("plan_key", sa.String(40), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("billing_provider", sa.String(40), nullable=False),
        sa.Column("external_customer_id", sa.String(180), unique=True),
        sa.Column("external_subscription_id", sa.String(180), unique=True),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True)),
        sa.Column("current_period_start", sa.DateTime(timezone=True)),
        sa.Column("current_period_end", sa.DateTime(timezone=True)),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_organization_subscriptions_organization_id", "organization_subscriptions", ["organization_id"], unique=True)
    op.create_index("ix_organization_subscriptions_plan_key", "organization_subscriptions", ["plan_key"])
    op.create_index("ix_organization_subscriptions_status", "organization_subscriptions", ["status"])
    op.create_table(
        "usage_counters",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("metric", sa.String(80), nullable=False),
        sa.Column("period_key", sa.String(10), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "metric", "period_key", name="uq_usage_org_metric_period"),
    )
    for column in ("organization_id", "metric", "period_key"):
        op.create_index(f"ix_usage_counters_{column}", "usage_counters", [column])
    op.create_table(
        "billing_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("provider_event_id", sa.String(180), nullable=False, unique=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("provider", "provider_event_id", "event_type"):
        op.create_index(f"ix_billing_events_{column}", "billing_events", [column], unique=column == "provider_event_id")

    bind = op.get_bind()
    now = datetime.now(UTC)
    organizations = bind.execute(sa.text("SELECT id FROM organizations")).mappings().all()
    for organization in organizations:
        bind.execute(sa.text("""
            INSERT INTO organization_subscriptions
            (id, organization_id, plan_key, status, billing_provider, trial_ends_at,
             current_period_start, current_period_end, cancel_at_period_end, created_at, updated_at)
            VALUES (:id, :organization_id, 'starter', 'trialing', 'manual', :trial_ends_at,
                    :now, :trial_ends_at, false, :now, :now)
        """), {"id": str(uuid.uuid4()), "organization_id": organization["id"], "now": now, "trial_ends_at": now + timedelta(days=14)})


def downgrade() -> None:
    op.drop_table("billing_events")
    op.drop_table("usage_counters")
    op.drop_table("organization_subscriptions")
