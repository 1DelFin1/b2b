from fastapi import APIRouter

from app.api.deps import SessionDep, ServiceKeyDep
from app.schemas import ReserveRequest, ReserveResponse, InventoryOrderRequest, InventoryOrderResponse
from app.services.inventory_service import InventoryService

inventory_router = APIRouter(prefix="/api/v1/inventory", tags=["inventory"])


@inventory_router.post("/reserve", response_model=ReserveResponse)
async def reserve_inventory(session: SessionDep, _: ServiceKeyDep, data: ReserveRequest):
    return await InventoryService.reserve(session, data)


@inventory_router.post("/unreserve", response_model=InventoryOrderResponse)
async def unreserve_inventory(session: SessionDep, _: ServiceKeyDep, data: InventoryOrderRequest):
    return await InventoryService.unreserve(session, data)


@inventory_router.post("/fulfill", response_model=InventoryOrderResponse)
async def fulfill_inventory(session: SessionDep, _: ServiceKeyDep, data: InventoryOrderRequest):
    return await InventoryService.fulfill(session, data)
