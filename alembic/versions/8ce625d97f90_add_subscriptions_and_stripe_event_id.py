"""add_subscriptions_and_stripe_event_id

Revision ID: 8ce625d97f90
Revises: d934303fb766
Create Date: 2026-04-23

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = '8ce625d97f90'
down_revision = 'd934303fb766'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'payments',
        sa.Column('stripe_event_id', sa.String(255), unique=True, nullable=True)
    )
    op.create_index('ix_payments_stripe_event_id', 'payments', ['stripe_event_id'])

    op.create_table(
        'subscriptions',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True, index=True),
        sa.Column('stripe_subscription_id', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('stripe_customer_id', sa.String(255), nullable=True, index=True),
        sa.Column('stripe_customer_email', sa.String(255), nullable=True),
        sa.Column('product', sa.String(50), nullable=True),
        sa.Column('tier', sa.String(50), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='active'),
        sa.Column('file_count', sa.Integer(), nullable=True),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('subscriptions')
    op.drop_index('ix_payments_stripe_event_id', table_name='payments')
    op.drop_column('payments', 'stripe_event_id')