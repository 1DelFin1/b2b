import enum
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


# ── Characteristics ───────────────────────────────────────────────────────────

class Characteristic(BaseModel):
    name: str
    value: str


class CharacteristicResponse(Characteristic):
    id: UUID


# ── Images ────────────────────────────────────────────────────────────────────

class ProductImageCreate(BaseModel):
    url: str
    ordering: int = 0


class SKUImageCreate(BaseModel):
    url: str
    ordering: int = 0


class ProductImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    url: str
    ordering: int


class SKUImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    url: str
    ordering: int


class ImageAttachRequest(BaseModel):
    image_id: UUID | None = None
    url: str
    ordering: int = 0


class ImageUpdateRequest(BaseModel):
    url: str | None = None
    ordering: int | None = None


class ImageEntityType(str, enum.Enum):
    PRODUCT = "PRODUCT"
    SKU = "SKU"


class ImageUploadResponse(BaseModel):
    id: UUID
    url: str
    ordering: int
    entity_type: ImageEntityType
    entity_id: UUID | None = None


# ── Category ──────────────────────────────────────────────────────────────────

class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: UUID | None = None


class CategoryUpdate(BaseModel):
    name: str | None = None
    parent_id: UUID | None = None
    is_active: bool | None = None


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    parent_id: UUID | None = None
    level: int
    path: str
    is_active: bool
    created_at: datetime


class CategoryWithChildrenResponse(CategoryResponse):
    children: list["CategoryResponse"] = []


class CategoryTreeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    children: list["CategoryTreeResponse"] = []


# ── Product ───────────────────────────────────────────────────────────────────

class CategoryShortResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str


class ProductCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=5000)
    category_id: UUID
    slug: str | None = None
    images: list[ProductImageCreate] = Field(default=[])
    characteristics: list[Characteristic] = []


class ProductUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    category_id: UUID | None = None
    characteristics: list[Characteristic] | None = None


class ProductShortResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    slug: str
    status: str
    category_id: UUID
    deleted: bool
    created_at: datetime
    min_price: int | None = None
    cover_image: str | None = None


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    seller_id: UUID
    category_id: UUID
    title: str
    slug: str | None
    description: str
    status: str
    deleted: bool
    blocking_reason_id: UUID | None = None
    moderator_comment: str | None = None
    images: list[ProductImageResponse] = []
    characteristics: list[CharacteristicResponse] = []
    skus: list["SKUResponse"] = []
    created_at: datetime
    updated_at: datetime


class ProductPublicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    seller_id: UUID
    category_id: UUID
    title: str
    slug: str | None
    description: str
    status: str
    images: list[ProductImageResponse] = []
    characteristics: list[CharacteristicResponse] = []
    skus: list["SKUPublicResponse"] = []
    created_at: datetime
    updated_at: datetime


class ProductPublicShortResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    slug: str | None
    status: str
    category_id: UUID
    min_price: int | None = None
    cover_image: str | None = None
    created_at: datetime


class ProductPaginatedResponse(BaseModel):
    items: list[ProductShortResponse]
    total_count: int
    limit: int
    offset: int


class ProductPublicPaginatedResponse(BaseModel):
    items: list[ProductPublicShortResponse]
    total_count: int
    limit: int
    offset: int


# ── SKU ───────────────────────────────────────────────────────────────────────

class SKUCreate(BaseModel):
    product_id: UUID
    name: str = Field(min_length=1, max_length=255)
    price: int = Field(ge=0)
    cost_price: int | None = None
    discount: int = Field(default=0, ge=0)
    images: list[SKUImageCreate] = []
    article: str | None = None
    characteristics: list[Characteristic] = []


class SKUUpdate(BaseModel):
    name: str | None = None
    price: int | None = Field(default=None, ge=0)
    cost_price: int | None = Field(default=None)
    discount: int | None = Field(default=None, ge=0)
    article: str | None = None
    characteristics: list[Characteristic] | None = None


class SKUResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    name: str
    price: int
    discount: int
    cost_price: int | None
    stock_quantity: int
    active_quantity: int
    reserved_quantity: int
    article: str | None
    images: list[SKUImageResponse] = []
    characteristics: list[CharacteristicResponse] = []
    created_at: datetime
    updated_at: datetime


class SKUPublicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    name: str
    price: int
    discount: int
    stock_quantity: int
    active_quantity: int
    article: str | None
    images: list[SKUImageResponse] = []
    characteristics: list[CharacteristicResponse] = []


# ── Invoice ───────────────────────────────────────────────────────────────────

class InvoiceItemCreate(BaseModel):
    sku_id: UUID
    quantity: int = Field(ge=1)


class InvoiceItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sku_id: UUID
    quantity: int
    accepted_quantity: int = 0


class InvoiceCreate(BaseModel):
    items: list[InvoiceItemCreate] = Field(min_length=1)


class InvoiceAcceptItemRequest(BaseModel):
    invoice_item_id: UUID
    accepted_quantity: int = Field(ge=0)


class InvoiceAcceptRequest(BaseModel):
    accepted_items: list[InvoiceAcceptItemRequest] | None = None


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    seller_id: UUID
    status: str
    items: list[InvoiceItemResponse] = []
    created_at: datetime
    updated_at: datetime
    accepted_at: datetime | None = None
    accepted_by: UUID | None = None


class InvoicePaginatedResponse(BaseModel):
    items: list[InvoiceResponse]
    total_count: int
    limit: int
    offset: int


# ── Inventory ─────────────────────────────────────────────────────────────────

class InventoryItem(BaseModel):
    sku_id: UUID
    quantity: int = Field(ge=1)


# Alias matching spec naming
InventoryItemRequest = InventoryItem


class ReserveRequest(BaseModel):
    idempotency_key: UUID
    order_id: UUID
    items: list[InventoryItem] = Field(min_length=1)


class ReserveItemResult(BaseModel):
    sku_id: UUID
    reserved_quantity: int
    remaining_stock: int


class ReserveFailedItem(BaseModel):
    sku_id: UUID
    requested: int
    available: int
    reason: str  # "OUT_OF_STOCK" | "INSUFFICIENT_STOCK"


class ReserveResult(BaseModel):
    reserved: bool
    items: list[ReserveItemResult] = []
    failed_items: list[ReserveFailedItem] = []


class ReserveResponse(BaseModel):
    order_id: UUID
    status: str = "RESERVED"
    reserved_at: datetime


class InventoryOrderRequest(BaseModel):
    order_id: UUID
    items: list[InventoryItem] = Field(min_length=1)


class InventoryOrderResponse(BaseModel):
    order_id: UUID
    status: str
    processed_at: datetime


# ── Moderation ────────────────────────────────────────────────────────────────

class FieldReport(BaseModel):
    field_name: str
    sku_id: UUID | None = None
    comment: str


class BlockingReasonResponse(BaseModel):
    id: UUID
    title: str
    comment: str | None = None


class BlockingReasonInput(BaseModel):
    id: UUID
    title: str
    comment: str | None = None


class ModerationEventRequest(BaseModel):
    idempotency_key: UUID
    product_id: UUID
    event_type: Literal["MODERATED", "BLOCKED"]
    moderator_id: UUID | None = None
    moderator_comment: str | None = None
    blocking_reason_id: UUID | None = None
    hard_block: bool = False
    field_reports: list[FieldReport] | None = None
    occurred_at: datetime


class BlockingReasonShortResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    hard_block: bool


# ── Canon B2B responses (match neomarket-protocols exactly) ──────────────────

class ImageCanonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    url: str
    ordering: int


class CharacteristicCanonResponse(BaseModel):
    name: str
    value: str


class SKUCanonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    name: str
    price: int
    cost_price: int | None
    discount: int
    active_quantity: int
    reserved_quantity: int
    images: list[ImageCanonResponse] = []
    characteristics: list[CharacteristicCanonResponse] = []


class ProductCanonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    seller_id: UUID
    title: str
    description: str
    status: str
    deleted: bool
    blocked: bool
    category: CategoryShortResponse
    images: list[ImageCanonResponse] = []
    characteristics: list[CharacteristicCanonResponse] = []
    skus: list[SKUCanonResponse] = []
    blocking_reason: BlockingReasonResponse | None = None
    field_reports: list[FieldReport] = []

    @model_validator(mode="before")
    @classmethod
    def _compose_blocking_reason(cls, data: object) -> object:
        br_id = getattr(data, "blocking_reason_id", None)
        br_title = getattr(data, "blocking_reason_title", None)
        if br_id is not None and br_title is not None and not getattr(data, "blocking_reason", None):
            d = {
                "id": getattr(data, "id", None),
                "seller_id": getattr(data, "seller_id", None),
                "title": getattr(data, "title", None),
                "description": getattr(data, "description", None),
                "status": getattr(data, "status", None),
                "deleted": getattr(data, "deleted", None),
                "blocked": getattr(data, "blocked", None),
                "category": getattr(data, "category", None),
                "images": getattr(data, "images", []),
                "characteristics": getattr(data, "characteristics", []),
                "skus": getattr(data, "skus", []),
                "field_reports": getattr(data, "field_reports", []),
                "blocking_reason": BlockingReasonResponse(
                    id=br_id,
                    title=br_title,
                    comment=getattr(data, "moderator_comment", None),
                ),
            }
            return d
        return data


# ── ProductDetailResponse (OpenAPI B2B ProductDetailResponse) ─────────────────

class ProductDetailResponse(BaseModel):
    """Seller-view карточки товара — полный ответ по канону B2B-5 и OpenAPI."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    seller_id: UUID
    category_id: UUID
    title: str
    slug: str | None
    description: str
    status: str
    deleted: bool
    blocked: bool
    images: list[ProductImageResponse] = []
    characteristics: list[CharacteristicResponse] = []
    skus: list[SKUResponse] = []
    created_at: datetime
    updated_at: datetime
    blocking_reason: BlockingReasonResponse | None = None
    field_reports: list[FieldReport] = []

    @model_validator(mode="before")
    @classmethod
    def _compose(cls, data: object) -> dict:
        if isinstance(data, dict):
            return data
        # Compose nested blocking_reason from flat ORM fields
        br_id = getattr(data, "blocking_reason_id", None)
        br_title = getattr(data, "blocking_reason_title", None)
        blocking_reason = (
            BlockingReasonResponse(
                id=br_id,
                title=br_title,
                comment=getattr(data, "moderator_comment", None),
            )
            if br_id is not None and br_title is not None
            else None
        )
        return {
            "id": data.id,
            "seller_id": data.seller_id,
            "category_id": data.category_id,
            "title": data.title,
            "slug": getattr(data, "slug", None),
            "description": data.description,
            "status": data.status,
            "deleted": data.deleted,
            "blocked": data.blocked,
            "images": getattr(data, "images", []),
            "characteristics": getattr(data, "characteristics", []),
            "skus": getattr(data, "skus", []),
            "created_at": data.created_at,
            "updated_at": data.updated_at,
            "blocking_reason": blocking_reason,
            "field_reports": getattr(data, "field_reports", []) or [],
        }


# ── Seller ────────────────────────────────────────────────────────────────────

class SellerCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = None
    company_name: str
    inn: str = Field(min_length=10, max_length=12)
    phone: str | None = None


class SellerUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None
    company_name: str | None = None
    phone: str | None = None


class SellerProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    first_name: str
    last_name: str
    middle_name: str | None = None
    company_name: str
    inn: str
    phone: str | None = None
    created_at: datetime
    updated_at: datetime


class BatchProductsRequest(BaseModel):
    product_ids: list[UUID] = Field(max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    user_id: UUID
