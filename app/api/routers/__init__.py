from app.api.routers.auth import auth_router
from app.api.routers.sellers import sellers_router
from app.api.routers.products import products_router
from app.api.routers.skus import skus_router, product_skus_router
from app.api.routers.categories import categories_router
from app.api.routers.images import images_router
from app.api.routers.invoices import invoices_router
from app.api.routers.inventory import inventory_router
from app.api.routers.public_catalog import public_router
from app.api.routers.moderation_events import moderation_events_router

__all__ = (
    "auth_router",
    "sellers_router",
    "products_router",
    "skus_router",
    "product_skus_router",
    "categories_router",
    "images_router",
    "invoices_router",
    "inventory_router",
    "public_router",
    "moderation_events_router",
)
