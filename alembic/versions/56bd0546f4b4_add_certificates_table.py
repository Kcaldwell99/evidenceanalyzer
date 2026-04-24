"""add_certificates_table

Revision ID: 56bd0546f4b4
Revises: 8ce625d97f90
Create Date: 2026-04-24

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = '56bd0546f4b4'
down_revision = '8ce625d97f90'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'certificates',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('certificate_id', sa.String(36), unique=True, nullable=False, index=True),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('case_id', sa.String(50), nullable=False, index=True),
        sa.Column('evidence_id', sa.String(50), nullable=True),
        sa.Column('generated_by', sa.String(255), nullable=True),
        sa.Column('pdf_key', sa.String(500), nullable=True),
        sa.Column('chain_verified_at_generation', sa.Boolean(), nullable=True),
        sa.Column('file_hash_at_generation', sa.String(128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('certificates')