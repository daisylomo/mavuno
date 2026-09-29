from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from mavuno.catalog.pagination import ListingCursor
from mavuno.db.models import (
    FarmerProfile,
    Fulfilment,
    InventoryMovement,
    Listing,
    ListingImage,
    ListingImageContent,
    Order,
    OrderItem,
    ProduceCategory,
    Product,
    Profile,
    User,
)


@dataclass(frozen=True, slots=True)
class FarmerFacts:
    user: User
    profile: Profile | None
    farmer: FarmerProfile | None
    active_listings: int
    completed_orders: int


Sort = Literal["newest", "price_asc", "price_desc"]


class CatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, value: Any) -> None:
        self.session.add(value)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, value: Any) -> None:
        await self.session.refresh(value)

    async def get_category(self, category_id: UUID) -> ProduceCategory | None:
        return await self.session.get(ProduceCategory, category_id)

    async def list_categories(self) -> list[ProduceCategory]:
        return list(
            await self.session.scalars(select(ProduceCategory).order_by(ProduceCategory.name))
        )

    async def get_product(self, product_id: UUID) -> Product | None:
        return await self.session.get(Product, product_id)

    async def list_products(self, category_id: UUID | None = None) -> list[Product]:
        query = select(Product).order_by(Product.name)
        if category_id is not None:
            query = query.where(Product.category_id == category_id)
        return list(await self.session.scalars(query))

    async def get_listing(self, listing_id: UUID, *, lock: bool = False) -> Listing | None:
        query = select(Listing).where(Listing.id == listing_id)
        if lock:
            query = query.with_for_update()
        return cast(Listing | None, await self.session.scalar(query))

    async def list_owned_listings(self, farmer_id: UUID) -> list[Listing]:
        return list(
            await self.session.scalars(
                select(Listing)
                .where(Listing.farmer_id == farmer_id, Listing.status != "archived")
                .order_by(Listing.created_at.desc(), Listing.id.desc())
                .limit(100)
            )
        )

    async def listing_context(
        self, listing: Listing
    ) -> tuple[Product, ProduceCategory, list[ListingImage]]:
        product = await self.session.get(Product, listing.product_id)
        if product is None:
            raise RuntimeError("Listing product is missing")
        category = await self.session.get(ProduceCategory, product.category_id)
        if category is None:
            raise RuntimeError("Product category is missing")
        images = list(
            await self.session.scalars(
                select(ListingImage)
                .where(ListingImage.listing_id == listing.id)
                .order_by(ListingImage.sort_order)
            )
        )
        return product, category, images

    async def list_listings(
        self,
        *,
        search: str | None,
        category_slug: str | None,
        farmer_id: UUID | None,
        unit: str | None,
        min_price: Decimal | None,
        max_price: Decimal | None,
        sort: Sort,
        cursor: ListingCursor | None,
        limit: int,
    ) -> list[Listing]:
        query = (
            select(Listing).join(Product).join(ProduceCategory).where(Listing.status == "active")
        )
        if search:
            pattern = f"%{search.lower()}%"
            query = query.where(or_(Listing.title.ilike(pattern), Product.name.ilike(pattern)))
        if category_slug:
            query = query.where(ProduceCategory.slug == category_slug)
        if farmer_id:
            query = query.where(Listing.farmer_id == farmer_id)
        if unit:
            query = query.where(Listing.quantity_unit == unit)
        if min_price is not None:
            query = query.where(Listing.price_amount >= min_price)
        if max_price is not None:
            query = query.where(Listing.price_amount <= max_price)
        query = self._cursor_order(query, sort, cursor)
        return list(await self.session.scalars(query.limit(limit + 1)))

    @staticmethod
    def _cursor_order(
        query: Select[tuple[Listing]], sort: Sort, cursor: ListingCursor | None
    ) -> Select[tuple[Listing]]:
        if sort == "newest":
            if cursor:
                created_value = datetime.fromisoformat(cursor.value)
                query = query.where(
                    or_(
                        Listing.created_at < created_value,
                        and_(
                            Listing.created_at == created_value,
                            Listing.id < cursor.listing_id,
                        ),
                    )
                )
            return query.order_by(Listing.created_at.desc(), Listing.id.desc())
        price_value = Decimal(cursor.value) if cursor else None
        if sort == "price_asc":
            if cursor and price_value is not None:
                query = query.where(
                    or_(
                        Listing.price_amount > price_value,
                        and_(
                            Listing.price_amount == price_value,
                            Listing.id > cursor.listing_id,
                        ),
                    )
                )
            return query.order_by(Listing.price_amount.asc(), Listing.id.asc())
        if cursor and price_value is not None:
            query = query.where(
                or_(
                    Listing.price_amount < price_value,
                    and_(
                        Listing.price_amount == price_value,
                        Listing.id < cursor.listing_id,
                    ),
                )
            )
        return query.order_by(Listing.price_amount.desc(), Listing.id.desc())

    async def optimistic_update(
        self, listing_id: UUID, version: int, values: dict[str, Any]
    ) -> bool:
        result = cast(
            CursorResult[Any],
            await self.session.execute(
                update(Listing)
                .where(Listing.id == listing_id, Listing.version == version)
                .values(**values, version=Listing.version + 1)
            ),
        )
        return bool(result.rowcount)

    async def delete_image(self, image: ListingImage) -> None:
        await self.session.delete(image)

    async def get_image(self, image_id: UUID) -> ListingImage | None:
        return await self.session.get(ListingImage, image_id)

    async def movements(self, listing_id: UUID) -> list[InventoryMovement]:
        return list(
            await self.session.scalars(
                select(InventoryMovement)
                .where(InventoryMovement.listing_id == listing_id)
                .order_by(InventoryMovement.created_at.desc())
            )
        )

    async def image_content(self, image_id: UUID) -> ListingImageContent | None:
        return await self.session.get(ListingImageContent, image_id)

    async def next_image_order(self, listing_id: UUID) -> int:
        value = await self.session.scalar(
            select(func.coalesce(func.max(ListingImage.sort_order) + 1, 0)).where(
                ListingImage.listing_id == listing_id
            )
        )
        return int(value or 0)

    async def farmer_facts(self, farmer_ids: set[UUID]) -> dict[UUID, FarmerFacts]:
        """Public facts about several farmers in three queries, for a page of listings."""
        if not farmer_ids:
            return {}
        rows = (
            await self.session.execute(
                select(User, Profile, FarmerProfile)
                .outerjoin(Profile, Profile.user_id == User.id)
                .outerjoin(FarmerProfile, FarmerProfile.user_id == User.id)
                .where(User.id.in_(farmer_ids))
            )
        ).all()
        active: dict[UUID, int] = {
            farmer_id: count
            for farmer_id, count in (
                await self.session.execute(
                    select(Listing.farmer_id, func.count(Listing.id))
                    .where(Listing.farmer_id.in_(farmer_ids), Listing.status == "active")
                    .group_by(Listing.farmer_id)
                )
            ).tuples()
        }
        completed: dict[UUID, int] = {
            farmer_id: count
            for farmer_id, count in (
                await self.session.execute(
                    select(OrderItem.farmer_id, func.count(func.distinct(OrderItem.order_id)))
                    .join(Order, Order.id == OrderItem.order_id)
                    .where(OrderItem.farmer_id.in_(farmer_ids), Order.status == "completed")
                    .group_by(OrderItem.farmer_id)
                )
            ).tuples()
        }
        return {
            user.id: FarmerFacts(
                user=user,
                profile=profile,
                farmer=farmer,
                active_listings=int(active.get(user.id, 0)),
                completed_orders=int(completed.get(user.id, 0)),
            )
            for user, profile, farmer in rows
        }

    async def farmer_categories(self, farmer_id: UUID) -> list[str]:
        return list(
            await self.session.scalars(
                select(ProduceCategory.name)
                .join(Product, Product.category_id == ProduceCategory.id)
                .join(Listing, Listing.product_id == Product.id)
                .where(Listing.farmer_id == farmer_id, Listing.status == "active")
                .distinct()
                .order_by(ProduceCategory.name)
            )
        )

    async def farmer_cancellations(self, farmer_id: UUID) -> int:
        value = await self.session.scalar(
            select(func.count(Fulfilment.id)).where(
                Fulfilment.farmer_id == farmer_id, Fulfilment.status == "cancelled"
            )
        )
        return int(value or 0)
