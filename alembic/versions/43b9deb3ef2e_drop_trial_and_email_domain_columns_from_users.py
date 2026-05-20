"""drop trial and email_domain columns from users

Revision ID: 43b9deb3ef2e
Revises: 85e7226497ff
Create Date: 2026-05-20

Drops six unused columns and two associated indexes from the users table.
All six columns were verified empty on prod before this migration was written:
    - trial_started_at        : 0/6 non-null
    - trial_expires_at        : 0/6 non-null
    - email_domain            : 0/6 non-null
    - trial_comparisons_used  : 6/6 non-null but all zeros
    - trial_web_searches_used : 6/6 non-null but all zeros
    - trial_certificates_used : 6/6 non-null but all zeros

Indexes dropped:
    - idx_users_email_domain
    - idx_users_trial_expires

Downgrade re-creates the columns and indexes but cannot recover original data
(none existed). Re-created columns are nullable with no default.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '43b9deb3ef2e'
down_revision = '85e7226497ff'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop indexes first so column drops don't have to cascade through them.
    op.drop_index('idx_users_email_domain', table_name='users')
    op.drop_index('idx_users_trial_expires', table_name='users')

    # Drop columns.
    op.drop_column('users', 'trial_comparisons_used')
    op.drop_column('users', 'trial_started_at')
    op.drop_column('users', 'trial_web_searches_used')
    op.drop_column('users', 'trial_certificates_used')
    op.drop_column('users', 'trial_expires_at')
    op.drop_column('users', 'email_domain')


def downgrade() -> None:
    # Re-add columns as nullable (no data to restore).
    op.add_column('users', sa.Column('email_domain', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('trial_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('trial_certificates_used', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('trial_web_searches_used', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('trial_started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('trial_comparisons_used', sa.Integer(), nullable=True))

    # Re-create indexes.
    op.create_index('idx_users_trial_expires', 'users', ['trial_expires_at'], unique=False)
    op.create_index('idx_users_email_domain', 'users', ['email_domain'], unique=False)
