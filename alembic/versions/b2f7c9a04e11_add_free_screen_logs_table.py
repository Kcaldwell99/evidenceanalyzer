"""add_free_screen_logs_table

Revision ID: b2f7c9a04e11
Revises: c75a1673e033
Create Date: 2026-06-19

Adds the free_screen_logs table backing the per-account monthly quota for the
free image screen (/screen). Images-only, ephemeral: stores only user_id,
created_at, c2pa_state, sha256 — no filename or media.

NOTE: local .env points at PRODUCTION Postgres. Do NOT `alembic upgrade head`
without explicit sign-off — that runs this migration against prod.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b2f7c9a04e11'
down_revision = 'c75a1673e033'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'free_screen_logs',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column('c2pa_state', sa.String(64), nullable=True),
        sa.Column('sha256', sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('free_screen_logs')
