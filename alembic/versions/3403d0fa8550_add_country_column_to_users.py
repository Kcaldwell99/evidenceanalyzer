"""add country column to users

Revision ID: 3403d0fa8550
Revises: 410c1f55ab6b
Create Date: 2026-05-16 16:39:58.270780

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3403d0fa8550'
down_revision: Union[str, Sequence[str], None] = '410c1f55ab6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('country', sa.String(length=2), nullable=True))
    op.create_index(op.f('ix_users_country'), 'users', ['country'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_users_country'), table_name='users')
    op.drop_column('users', 'country')
