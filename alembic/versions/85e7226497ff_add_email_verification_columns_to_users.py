"""add email verification columns to users

Revision ID: 85e7226497ff
Revises: e5b971b8da6a
Create Date: 2026-05-18 19:42:55.108454

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '85e7226497ff'
down_revision: Union[str, Sequence[str], None] = 'e5b971b8da6a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'users',
        sa.Column('email_verified', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    op.add_column(
        'users',
        sa.Column('email_verification_token', sa.String(length=128), nullable=True),
    )
    op.add_column(
        'users',
        sa.Column('email_verification_token_expires', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        'ix_users_email_verification_token',
        'users',
        ['email_verification_token'],
    )
    op.alter_column('users', 'email_verified', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_users_email_verification_token', table_name='users')
    op.drop_column('users', 'email_verification_token_expires')
    op.drop_column('users', 'email_verification_token')
    op.drop_column('users', 'email_verified')
