from fastapi import APIRouter, File, UploadFile, status

from app.api.deps import SessionDep, SellerDep, get_seller_id
from app.exceptions import SELLER_NOT_FOUND
from app.schemas import SellerUpdate, SellerProfileResponse
from app.services.seller_service import SellerService

sellers_router = APIRouter(prefix="/api/v1/sellers", tags=["sellers"])


@sellers_router.get("/me", response_model=SellerProfileResponse)
async def get_current_seller(session: SessionDep, payload: SellerDep):
    seller_id = get_seller_id(payload)
    seller = await SellerService.get_seller_by_id(session, seller_id, sync_metrics=True)
    if seller is None:
        raise SELLER_NOT_FOUND
    return seller


@sellers_router.patch("/me", response_model=SellerProfileResponse)
async def update_current_seller(session: SessionDep, payload: SellerDep, data: SellerUpdate):
    seller_id = get_seller_id(payload)
    await SellerService.update(session, data, seller_id)
    seller = await SellerService.get_seller_by_id(session, seller_id, sync_metrics=False)
    if seller is None:
        raise SELLER_NOT_FOUND
    return seller


@sellers_router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_current_seller(session: SessionDep, payload: SellerDep):
    seller_id = get_seller_id(payload)
    await SellerService.delete(session, seller_id)


@sellers_router.post("/me/photo", response_model=SellerProfileResponse)
async def upload_seller_photo(
    session: SessionDep,
    payload: SellerDep,
    file: UploadFile = File(...),
):
    seller_id = get_seller_id(payload)
    return await SellerService.upload_seller_photo(session, seller_id, file)
