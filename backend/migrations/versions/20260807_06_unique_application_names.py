"""Require unique application names within an organization.

Revision ID: 20260807_06
Revises: 20260807_05
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260807_06"
down_revision: str | None = "20260807_05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_applications_organization_normalized_name",
        "applications",
        ["organization_id", sa.text("lower(btrim(name))")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_applications_organization_normalized_name", table_name="applications")
