"""add web_detection_enabled to evidence_items

Revision ID: 410c1f55ab6b
Revises: 56bd0546f4b4
Create Date: 2026-05-15 16:26:16.121676

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '410c1f55ab6b'
down_revision: Union[str, Sequence[str], None] = '56bd0546f4b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('evidence_items', sa.Column('web_detection_enabled', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('evidence_items', 'web_detection_enabled')
