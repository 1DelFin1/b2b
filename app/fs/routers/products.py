from faststream.rabbit import RabbitRouter

from app.core.rabbit_config import (
    products_reserved_queue,
    products_delete_queue,
    reviews_queue,
    orders_reserved_queue,
)
from app.services.product_service import ProductService

products_router = RabbitRouter()


@products_router.subscriber(products_reserved_queue)
async def reserve_products(products: dict):
    await ProductService.reserve_product(products)


@products_router.subscriber(products_delete_queue)
async def delete_products(order: dict):
    await ProductService.handle_paid_products(order)


@products_router.subscriber(reviews_queue)
async def handle_review_event(event: dict):
    await ProductService.handle_review_changed(event)


@products_router.subscriber(orders_reserved_queue)
async def handle_orders_reserved(order: dict):
    await ProductService.reserve_product(order)
