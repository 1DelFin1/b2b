from faststream import FastStream

from app.core.rabbit_config import rabbit_broker
from app.fs.routers import products_router

app = FastStream(rabbit_broker)

rabbit_broker.include_router(products_router)
