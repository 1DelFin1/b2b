from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import SessionDep, SellerDep, AdminDep, get_seller_id
from app.schemas import InvoiceCreate, InvoiceAcceptRequest, InvoiceResponse, InvoicePaginatedResponse
from app.services.invoice_service import InvoiceService

invoices_router = APIRouter(prefix="/api/v1/invoices", tags=["invoices"])


@invoices_router.get("", response_model=InvoicePaginatedResponse)
async def list_invoices(
    session: SessionDep,
    payload: SellerDep,
    status: Annotated[Literal["PENDING", "PARTIALLY_ACCEPTED", "ACCEPTED", "CANCELLED"] | None, Query()] = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    seller_id = get_seller_id(payload)
    items, total = await InvoiceService.get_list(
        session, seller_id=seller_id, status=status, limit=limit, offset=offset
    )
    return InvoicePaginatedResponse(items=items, total_count=total, limit=limit, offset=offset)


@invoices_router.post("", response_model=InvoiceResponse, status_code=201)
async def create_invoice(session: SessionDep, payload: SellerDep, data: InvoiceCreate):
    seller_id = get_seller_id(payload)
    return await InvoiceService.create(session, seller_id=seller_id, data=data)


@invoices_router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(invoice_id: UUID, session: SessionDep, payload: SellerDep):
    seller_id = get_seller_id(payload)
    return await InvoiceService.get_by_id(session, invoice_id=invoice_id, seller_id=seller_id)


@invoices_router.post("/{invoice_id}/accept", response_model=InvoiceResponse)
async def accept_invoice(
    invoice_id: UUID,
    session: SessionDep,
    payload: AdminDep,
    data: InvoiceAcceptRequest | None = None,
):
    accepted_by = get_seller_id(payload)
    return await InvoiceService.accept(session, invoice_id=invoice_id, accepted_by=accepted_by, data=data)


@invoices_router.delete("/{invoice_id}", status_code=204)
async def cancel_invoice(invoice_id: UUID, session: SessionDep, payload: SellerDep):
    seller_id = get_seller_id(payload)
    await InvoiceService.cancel(session, invoice_id=invoice_id, seller_id=seller_id)
