"""Add endpoint signatures and operational alerts.

Revision ID: 20260807_05
Revises: 20260807_04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260807_05"
down_revision: str | None = "20260807_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("endpoints", sa.Column("signing_secret", sa.String(128), nullable=True))
    op.execute(
        "UPDATE endpoints SET signing_secret = 'whsec_' || "
        "md5(random()::text || clock_timestamp()::text || id::text) "
        "WHERE signing_secret IS NULL"
    )
    op.alter_column("endpoints", "signing_secret", nullable=False)
    op.create_table(
        "operational_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("delivery_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["delivery_id"], ["webhook_deliveries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_operational_alerts_application_id", "operational_alerts", ["application_id"]
    )
    op.create_index(
        "ix_operational_alerts_delivery_id", "operational_alerts", ["delivery_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_operational_alerts_delivery_id", table_name="operational_alerts")
    op.drop_index("ix_operational_alerts_application_id", table_name="operational_alerts")
    op.drop_table("operational_alerts")
    op.drop_column("endpoints", "signing_secret")
