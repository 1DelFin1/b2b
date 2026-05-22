"""initial

Revision ID: 0001
Revises:
Create Date: 2026-05-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'sellers',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('first_name', sa.String(100), nullable=False),
        sa.Column('last_name', sa.String(100), nullable=False),
        sa.Column('middle_name', sa.String(100), nullable=True),
        sa.Column('company_name', sa.String(255), nullable=False),
        sa.Column('inn', sa.String(12), nullable=False),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('photo_url', sa.String(1024), nullable=True),
        sa.Column('hashed_password', sa.String(), nullable=False),
        sa.Column('rating', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('orders_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_sellers_email', 'sellers', ['email'], unique=True)

    op.create_table(
        'refresh_tokens',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('token', sa.String(64), nullable=False),
        sa.Column('account_id', sa.String(36), nullable=False),
        sa.Column('account_type', sa.String(10), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_refresh_tokens_token', 'refresh_tokens', ['token'], unique=True)

    op.create_table(
        'categories',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('parent_id', UUID(as_uuid=True), sa.ForeignKey('categories.id', ondelete='SET NULL'), nullable=True),
        sa.Column('level', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('path', sa.String(1000), nullable=False, server_default="''"),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    op.create_table(
        'products',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('seller_id', UUID(as_uuid=True), nullable=False),
        sa.Column('category_id', UUID(as_uuid=True), sa.ForeignKey('categories.id'), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(300), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='CREATED'),
        sa.Column('deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('blocking_reason_id', UUID(as_uuid=True), nullable=True),
        sa.Column('blocking_reason_title', sa.String(500), nullable=True),
        sa.Column('moderator_comment', sa.Text(), nullable=True),
        sa.Column('field_reports', sa.JSON(), nullable=False, server_default="'[]'::json"),
        sa.Column('characteristics', sa.JSON(), nullable=False, server_default="'[]'::json"),
        sa.Column('rating', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('total_reviews', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_products_seller_id', 'products', ['seller_id'])
    op.create_index('ix_products_slug', 'products', ['slug'])

    op.create_table(
        'product_images',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('product_id', UUID(as_uuid=True), sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('url', sa.String(1024), nullable=False),
        sa.Column('alt', sa.String(255), nullable=True),
        sa.Column('ordering', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_main', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.create_index('ix_product_images_product_id', 'product_images', ['product_id'])

    op.create_table(
        'skus',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('product_id', UUID(as_uuid=True), sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('price', sa.Integer(), nullable=False),
        sa.Column('discount', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cost_price', sa.Integer(), nullable=True),
        sa.Column('stock_quantity', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reserved_quantity', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('article', sa.String(100), nullable=True),
        sa.Column('characteristics', sa.JSON(), nullable=False, server_default="'[]'::json"),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_skus_product_id', 'skus', ['product_id'])

    op.create_table(
        'sku_images',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('sku_id', UUID(as_uuid=True), sa.ForeignKey('skus.id', ondelete='CASCADE'), nullable=False),
        sa.Column('url', sa.String(1024), nullable=False),
        sa.Column('alt', sa.String(255), nullable=True),
        sa.Column('ordering', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_index('ix_sku_images_sku_id', 'sku_images', ['sku_id'])

    op.create_table(
        'invoices',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('seller_id', UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(25), nullable=False, server_default='CREATED'),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('accepted_by', UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_invoices_seller_id', 'invoices', ['seller_id'])

    op.create_table(
        'invoice_items',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('invoice_id', UUID(as_uuid=True), sa.ForeignKey('invoices.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sku_id', UUID(as_uuid=True), nullable=False),
        sa.Column('sku_name', sa.String(255), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('accepted_quantity', sa.Integer(), nullable=True),
    )
    op.create_index('ix_invoice_items_invoice_id', 'invoice_items', ['invoice_id'])

    op.create_table(
        'reserved_products',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('sku_id', UUID(as_uuid=True), sa.ForeignKey('skus.id', ondelete='CASCADE'), nullable=False),
        sa.Column('order_id', UUID(as_uuid=True), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('idempotency_key', UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_reserved_products_sku_id', 'reserved_products', ['sku_id'])
    op.create_index('ix_reserved_products_order_id', 'reserved_products', ['order_id'])


def downgrade() -> None:
    op.drop_table('reserved_products')
    op.drop_table('invoice_items')
    op.drop_table('invoices')
    op.drop_table('sku_images')
    op.drop_table('skus')
    op.drop_table('product_images')
    op.drop_table('products')
    op.drop_table('categories')
    op.drop_table('refresh_tokens')
    op.drop_table('sellers')
