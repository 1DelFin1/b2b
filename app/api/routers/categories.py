from uuid import UUID

from fastapi import APIRouter

from app.api.deps import SessionDep, AdminDep
from app.schemas import CategoryCreate, CategoryUpdate, CategoryResponse, CategoryTreeResponse, CategoryWithChildrenResponse
from app.services.category_service import CategoryService

categories_router = APIRouter(prefix="/api/v1/categories", tags=["categories"])


async def _get_all(session: SessionDep, parent_id: UUID | None = None, only_root: bool = False):
    cats = await CategoryService.get_all(session, parent_id=parent_id, only_root=only_root)
    return cats


async def _get_tree(session: SessionDep):
    return await CategoryService.get_tree(session)


async def _get_one_with_children(category_id: UUID, session: SessionDep) -> CategoryWithChildrenResponse:
    result = await CategoryService.get_by_id_with_children(session, category_id)
    cat = result["category"]
    return CategoryWithChildrenResponse.model_validate(cat).model_copy(
        update={"children": [CategoryResponse.model_validate(c) for c in result["children"]]}
    )


async def _get_breadcrumbs(category_id: UUID, session: SessionDep):
    return await CategoryService.get_breadcrumbs(session, category_id)


async def _create(session: SessionDep, data: CategoryCreate, payload: AdminDep) -> CategoryWithChildrenResponse:
    cat = await CategoryService.create(session, data)
    return CategoryWithChildrenResponse.model_validate(cat).model_copy(update={"children": []})


async def _update(category_id: UUID, session: SessionDep, data: CategoryUpdate, payload: AdminDep) -> CategoryWithChildrenResponse:
    result = await CategoryService.get_by_id_with_children(session, category_id)
    cat = await CategoryService.update(session, category_id, data)
    children = result["children"]
    return CategoryWithChildrenResponse.model_validate(cat).model_copy(
        update={"children": [CategoryResponse.model_validate(c) for c in children]}
    )


@categories_router.get("", response_model=list[CategoryResponse])
async def get_all_categories(session: SessionDep, parent_id: UUID | None = None, only_root: bool = False):
    return await _get_all(session, parent_id, only_root)


@categories_router.get("/tree", response_model=list[CategoryTreeResponse])
async def get_categories_tree(session: SessionDep):
    return await _get_tree(session)


@categories_router.get("/{category_id}", response_model=CategoryWithChildrenResponse)
async def get_category(category_id: UUID, session: SessionDep):
    return await _get_one_with_children(category_id, session)


@categories_router.get("/{category_id}/breadcrumbs", response_model=list[CategoryResponse])
async def get_category_breadcrumbs(category_id: UUID, session: SessionDep):
    return await _get_breadcrumbs(category_id, session)


@categories_router.post("", response_model=CategoryWithChildrenResponse, status_code=201)
async def create_category(session: SessionDep, data: CategoryCreate, payload: AdminDep):
    return await _create(session, data, payload)


@categories_router.patch("/{category_id}", response_model=CategoryWithChildrenResponse)
async def update_category(category_id: UUID, session: SessionDep, data: CategoryUpdate, payload: AdminDep):
    return await _update(category_id, session, data, payload)


@categories_router.delete("/{category_id}", status_code=204)
async def delete_category(category_id: UUID, session: SessionDep, payload: AdminDep):
    await CategoryService.delete(session, category_id)
