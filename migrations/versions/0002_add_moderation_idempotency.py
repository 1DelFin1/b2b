"""add last_moderation_idempotency_key to products

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-31

"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'products',
        sa.Column('last_moderation_idempotency_key', sa.String(36), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('products', 'last_moderation_idempotency_key')
