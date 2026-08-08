"""Create durable webhook deliveries.

Revision ID: 20260807_04
Revises: 20260807_03
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260807_04"
down_revision: str | None = "20260807_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    delivery_status = sa.Enum("pending", "succeeded", "dead", name="delivery_status")
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", delivery_status, nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["endpoint_id"], ["endpoints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["webhook_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "endpoint_id"),
    )
    op.create_index(
        op.f("ix_webhook_deliveries_endpoint_id"), "webhook_deliveries", ["endpoint_id"]
    )
    op.create_index(op.f("ix_webhook_deliveries_event_id"), "webhook_deliveries", ["event_id"])
    op.create_index(
        op.f("ix_webhook_deliveries_next_attempt_at"), "webhook_deliveries", ["next_attempt_at"]
    )


def downgrade() -> None:
    op.drop_table("webhook_deliveries")
    sa.Enum(name="delivery_status").drop(op.get_bind())
