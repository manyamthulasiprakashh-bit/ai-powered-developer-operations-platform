"""create analyses table

Revision ID: 0001_create_analyses
Revises:
Create Date: 2026-10-19

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001_create_analyses"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analyses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner", sa.String(length=100), nullable=False),
        sa.Column("repository", sa.String(length=100), nullable=False),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analyses_owner", "analyses", ["owner"])
    op.create_index("ix_analyses_repository", "analyses", ["repository"])


def downgrade() -> None:
    op.drop_index("ix_analyses_repository", table_name="analyses")
    op.drop_index("ix_analyses_owner", table_name="analyses")
    op.drop_table("analyses")
