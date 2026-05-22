from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.categories import CategoryModel
from app.models.products import ProductModel
from app.schemas import CategoryCreate, CategoryUpdate


class CategoryService:
    @staticmethod
    async def _build_path(session: AsyncSession, parent_id: UUID | None, name: str) -> tuple[int, str]:
        if parent_id is None:
            return 0, name.lower().replace(" ", "_")
        parent = await session.get(CategoryModel, parent_id)
        if not parent:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent category not found")
        slug = name.lower().replace(" ", "_")
        return parent.level + 1, f"{parent.path}/{slug}"

    @classmethod
    async def get_all(cls, session: AsyncSession, parent_id: UUID | None = None, only_root: bool = False) -> list[CategoryModel]:
        stmt = select(CategoryModel)
        if only_root:
            stmt = stmt.where(CategoryModel.parent_id.is_(None))
        elif parent_id is not None:
            stmt = stmt.where(CategoryModel.parent_id == parent_id)
        stmt = stmt.order_by(CategoryModel.name)
        return list((await session.scalars(stmt)).all())

    @classmethod
    async def get_tree(cls, session: AsyncSession) -> list[dict]:
        all_cats = list((await session.scalars(select(CategoryModel))).all())
        children_map: dict[UUID | None, list] = {}
        for cat in all_cats:
            children_map.setdefault(cat.parent_id, []).append(cat)

        def build_node(cat: CategoryModel) -> dict:
            return {
                "id": cat.id,
                "name": cat.name,
                "children": [build_node(c) for c in children_map.get(cat.id, [])],
            }

        return [build_node(c) for c in children_map.get(None, [])]

    @classmethod
    async def get_by_id(cls, session: AsyncSession, category_id: UUID) -> CategoryModel:
        cat = await session.get(CategoryModel, category_id)
        if not cat:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
        return cat

    @classmethod
    async def get_by_id_with_children(cls, session: AsyncSession, category_id: UUID) -> dict:
        cat = await cls.get_by_id(session, category_id)
        children = list((await session.scalars(
            select(CategoryModel).where(CategoryModel.parent_id == category_id).order_by(CategoryModel.name)
        )).all())
        return {"category": cat, "children": children}

    @classmethod
    async def get_breadcrumbs(cls, session: AsyncSession, category_id: UUID) -> list[CategoryModel]:
        result = []
        current_id: UUID | None = category_id
        while current_id is not None:
            cat = await session.get(CategoryModel, current_id)
            if not cat:
                break
            result.insert(0, cat)
            current_id = cat.parent_id
        return result

    @classmethod
    async def create(cls, session: AsyncSession, data: CategoryCreate) -> CategoryModel:
        level, path = await cls._build_path(session, data.parent_id, data.name)
        cat = CategoryModel(name=data.name, parent_id=data.parent_id, level=level, path=path)
        session.add(cat)
        await session.commit()
        await session.refresh(cat)
        return cat

    @classmethod
    async def update(cls, session: AsyncSession, category_id: UUID, data: CategoryUpdate) -> CategoryModel:
        cat = await cls.get_by_id(session, category_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(cat, field, value)
        if data.name is not None or data.parent_id is not None:
            name = data.name or cat.name
            parent_id = data.parent_id if data.parent_id is not None else cat.parent_id
            cat.level, cat.path = await cls._build_path(session, parent_id, name)
        await session.commit()
        await session.refresh(cat)
        return cat

    @classmethod
    async def delete(cls, session: AsyncSession, category_id: UUID) -> None:
        cat = await cls.get_by_id(session, category_id)
        count = await session.scalar(
            select(func.count(ProductModel.id)).where(ProductModel.category_id == category_id)
        )
        if (count or 0) > 0:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category has products")
        await session.delete(cat)
        await session.commit()
