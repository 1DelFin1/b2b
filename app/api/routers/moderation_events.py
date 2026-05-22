from fastapi import APIRouter, status

from app.api.deps import SessionDep, ServiceKeyDep
from app.schemas import ModerationEventRequest
from app.services.product_service import ProductService

moderation_events_router = APIRouter(prefix="/api/v1/moderation", tags=["moderation-events"])


@moderation_events_router.post("/events", status_code=status.HTTP_204_NO_CONTENT)
async def receive_moderation_event(
    _: ServiceKeyDep,
    session: SessionDep,
    event: ModerationEventRequest,
):
    await ProductService.apply_moderation_event(session, event)
