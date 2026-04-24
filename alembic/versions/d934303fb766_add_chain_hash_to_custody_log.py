"""add_chain_hash_to_custody_log

Revision ID: d934303fb766
Revises: 
Create Date: 2026-04-23

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = 'd934303fb766'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'custody_log',
        sa.Column('chain_hash', sa.String(64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('custody_log', 'chain_hash')