"""add cookie_consent column to users

Revision ID: e5b971b8da6a
Revises: 3403d0fa8550
Create Date: 2026-05-17 07:43:45.155275

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e5b971b8da6a'
down_revision: Union[str, Sequence[str], None] = '3403d0fa8550'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('cookie_consent', sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'cookie_consent')
