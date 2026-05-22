import uvicorn
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.api.routers import (
    auth_router,
    sellers_router,
    products_router,
    skus_router,
    product_skus_router,
    categories_router,
    images_router,
    invoices_router,
    inventory_router,
    public_router,
    moderation_events_router,
)
from app.core.config import settings
from app.core.rabbit_config import rabbit_broker
from app.scheduler import scheduler, configure_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)

    configure_scheduler()
    if not scheduler.running:
        scheduler.start()

    await rabbit_broker.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)
    await rabbit_broker.close()


app = FastAPI(
    title="b2b",
    lifespan=lifespan,
    swagger_ui_parameters={"persistAuthorization": True},
)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version="1.0.0",
        routes=app.routes,
    )
    schema.setdefault("components", {}).setdefault("securitySchemes", {})["HTTPBearer"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }
    schema["security"] = [{"HTTPBearer": []}]
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi

app.include_router(auth_router)
app.include_router(sellers_router)
app.include_router(products_router)
app.include_router(skus_router)
app.include_router(product_skus_router)
app.include_router(categories_router)
app.include_router(images_router)
app.include_router(invoices_router)
app.include_router(inventory_router)
app.include_router(public_router)
app.include_router(moderation_events_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=settings.cors.CORS_METHODS,
    allow_headers=settings.cors.CORS_HEADERS,
)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8010, reload=True)
