"""add_payment_entitlement_columns

Revision ID: a3f1d9c2b8e4
Revises: b2f7c9a04e11
Create Date: 2026-06-20

Adds three nullable columns to the payments table to support file-specific
Integrity Certificate entitlement (Model A, file-specific paywall):
    user_id     - FK to users.id, set by webhook from Stripe session metadata
    case_id     - string business key, mirrors evidence_items.case_id
    evidence_id - string business key, mirrors evidence_items.evidence_id

Additive only. All columns nullable. NO unique constraint by design: the
payments insert path is insert-always and existing duplicate rows would make
a unique constraint fail to build and would break cert regeneration. The
entitlement gate enforces correctness in code (assert_cert_entitlement +
SELECT ... FOR UPDATE row lock), not via a DB constraint.

Indexes are created explicitly via op.create_index (inline index=True on
op.add_column is not reliably honored across alembic/sqlalchemy versions).

No backfill: zero legacy paid Integrity Certificates exist.

NOTE: local .env points at PRODUCTION Postgres. Do NOT `alembic upgrade head`
without explicit sign-off -- that runs this migration against prod.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a3f1d9c2b8e4'
down_revision = 'b2f7c9a04e11'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('payments', sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True))
    op.add_column('payments', sa.Column('case_id', sa.String(50), nullable=True))
    op.add_column('payments', sa.Column('evidence_id', sa.String(50), nullable=True))
    op.create_index('ix_payments_user_id', 'payments', ['user_id'])
    op.create_index('ix_payments_case_id', 'payments', ['case_id'])
    op.create_index('ix_payments_evidence_id', 'payments', ['evidence_id'])


def downgrade() -> None:
    op.drop_index('ix_payments_evidence_id', table_name='payments')
    op.drop_index('ix_payments_case_id', table_name='payments')
    op.drop_index('ix_payments_user_id', table_name='payments')
    op.drop_column('payments', 'evidence_id')
    op.drop_column('payments', 'case_id')
    op.drop_column('payments', 'user_id')