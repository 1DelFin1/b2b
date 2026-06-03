"""rename invoice status PENDING to CREATED

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-03

"""
from alembic import op

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE invoices SET status = 'CREATED' WHERE status = 'PENDING'")


def downgrade() -> None:
    op.execute("UPDATE invoices SET status = 'PENDING' WHERE status = 'CREATED'")
