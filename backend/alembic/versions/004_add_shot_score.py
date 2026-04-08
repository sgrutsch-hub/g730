"""Add shot_score to shots for weighted performance scoring.

Revision ID: 004
Revises: 003
Create Date: 2026-04-08
"""

import sqlalchemy as sa
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("shots", sa.Column("shot_score", sa.Numeric(4, 1), nullable=True))


def downgrade() -> None:
    op.drop_column("shots", "shot_score")
