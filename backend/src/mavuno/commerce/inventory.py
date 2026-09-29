"""Stock reservation shared by checkout, expiry, cancellation and late payment."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID, uuid4

from mavuno.commerce.repository import CommerceRepository
from mavuno.db.models import InventoryMovement, OrderItem


async def release(
    repository: CommerceRepository,
    items: Iterable[OrderItem],
    *,
    order_id: UUID,
    actor_user_id: UUID,
    reason: str,
) -> set[UUID]:
    """Return reserved stock to its listings. Returns the listings that changed."""
    changed: set[UUID] = set()
    for item in sorted(items, key=lambda value: value.listing_id.bytes):
        listing = await repository.listing(item.listing_id, lock=True)
        if listing is None:
            raise RuntimeError("Reserved listing is missing")
        listing.available_quantity += item.quantity
        listing.version += 1
        if listing.status == "sold_out":
            listing.status = "active"
        repository.add(
            InventoryMovement(
                id=uuid4(),
                listing_id=listing.id,
                actor_user_id=actor_user_id,
                movement_type="release",
                quantity_delta=item.quantity,
                resulting_quantity=listing.available_quantity,
                reason=reason[:255],
                reference_type="order",
                reference_id=order_id,
            )
        )
        changed.add(listing.id)
    return changed


async def reserve_again(
    repository: CommerceRepository,
    items: list[OrderItem],
    *,
    order_id: UUID,
    actor_user_id: UUID,
    reason: str,
) -> set[UUID] | None:
    """Take stock back for an order whose reservation lapsed.

    Every line must still be available on a sellable listing, otherwise nothing changes and
    ``None`` is returned: a paid order is never fulfilled from stock that was sold to others.
    """
    ordered = sorted(items, key=lambda value: value.listing_id.bytes)
    listings = []
    for item in ordered:
        listing = await repository.listing(item.listing_id, lock=True)
        if (
            listing is None
            or listing.status not in {"active", "sold_out"}
            or listing.available_quantity < item.quantity
        ):
            return None
        listings.append(listing)
    changed: set[UUID] = set()
    for item, listing in zip(ordered, listings, strict=True):
        listing.available_quantity -= item.quantity
        listing.version += 1
        if listing.available_quantity == 0:
            listing.status = "sold_out"
        repository.add(
            InventoryMovement(
                id=uuid4(),
                listing_id=listing.id,
                actor_user_id=actor_user_id,
                movement_type="reservation",
                quantity_delta=-item.quantity,
                resulting_quantity=listing.available_quantity,
                reason=reason[:255],
                reference_type="order",
                reference_id=order_id,
            )
        )
        changed.add(listing.id)
    return changed
