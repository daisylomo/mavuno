from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete, select

from mavuno.api.dependencies import get_current_user
from mavuno.api.errors import ApiError
from mavuno.auth.context import AuthenticatedUser
from mavuno.catalog.repository import CatalogRepository
from mavuno.catalog.schemas import ListingUpdate
from mavuno.catalog.service import CatalogService
from mavuno.core.config import Settings
from mavuno.db import Database
from mavuno.db.models import (
    InventoryMovement,
    Listing,
    ProduceCategory,
    Product,
    User,
    UserRole,
)
from mavuno.main import create_app

TEST_DATABASE_URL = os.getenv("MAVUNO_TEST_DATABASE_URL")
TEST_REDIS_URL = os.getenv("MAVUNO_TEST_REDIS_URL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="MAVUNO_TEST_DATABASE_URL is not set"),
]


def test_catalog_http_contract_and_cache_headers() -> None:
    assert TEST_DATABASE_URL is not None
    user_id = uuid4()
    actor = AuthenticatedUser(
        user_id,
        "catalog@example.test",
        None,
        frozenset({"administrator", "farmer"}),
        0,
    )

    async def prepare() -> None:
        database = Database(Settings(environment="test", database_url=SecretStr(TEST_DATABASE_URL)))
        try:
            async with database.session() as session:
                session.add(
                    User(
                        id=user_id,
                        email=f"{user_id}@example.test",
                        password_hash="x",
                        status="active",
                    )
                )
                await session.commit()
        finally:
            await database.dispose()

    async def cleanup(listing_id: str, product_id: str, category_id: str) -> None:
        database = Database(Settings(environment="test", database_url=SecretStr(TEST_DATABASE_URL)))
        try:
            async with database.session() as session:
                listing_uuid = UUID(listing_id)
                await session.execute(
                    delete(InventoryMovement).where(InventoryMovement.listing_id == listing_uuid)
                )
                await session.execute(delete(Listing).where(Listing.id == listing_uuid))
                await session.execute(delete(Product).where(Product.id == UUID(product_id)))
                await session.execute(
                    delete(ProduceCategory).where(ProduceCategory.id == UUID(category_id))
                )
                await session.execute(delete(User).where(User.id == user_id))
                await session.commit()
        finally:
            await database.dispose()

    asyncio.run(prepare())
    app = create_app(
        Settings(
            environment="test",
            database_url=SecretStr(TEST_DATABASE_URL),
            redis_url=SecretStr(TEST_REDIS_URL) if TEST_REDIS_URL else None,
        )
    )

    async def authenticated() -> AuthenticatedUser:
        return actor

    app.dependency_overrides[get_current_user] = authenticated
    category_id = product_id = listing_id = ""
    try:
        with TestClient(app) as client:
            category = client.post(
                "/api/v1/catalog/categories",
                json={"name": "Root crops", "slug": f"root-crops-{uuid4()}"},
            )
            assert category.status_code == 201
            category_id = category.json()["id"]
            assert client.get("/api/v1/catalog/categories").status_code == 200

            product = client.post(
                "/api/v1/catalog/products",
                json={
                    "category_id": category_id,
                    "name": "Sweet potato",
                    "slug": f"sweet-potato-{uuid4()}",
                    "default_unit": "kg",
                },
            )
            assert product.status_code == 201
            product_id = product.json()["id"]
            assert (
                client.get(
                    "/api/v1/catalog/products", params={"category_id": category_id}
                ).status_code
                == 200
            )

            created = client.post(
                "/api/v1/listings",
                json={
                    "product_id": product_id,
                    "title": "Fresh sweet potatoes",
                    "price_amount": "90.00",
                    "available_quantity": "10",
                    "quantity_unit": "kg",
                },
            )
            assert created.status_code == 201
            listing_id = created.json()["id"]

            activated = client.patch(
                f"/api/v1/listings/{listing_id}",
                json={"expected_version": 1, "status": "active"},
            )
            assert activated.status_code == 200
            assert activated.json()["version"] == 2

            image = client.post(
                f"/api/v1/listings/{listing_id}/images",
                json={"object_key": "listings/sweet-potato.jpg", "sort_order": 0},
            )
            assert image.status_code == 201

            page = client.get("/api/v1/listings", params={"category": category.json()["slug"]})
            assert page.status_code == 200
            assert page.headers["cache-control"].startswith("public")
            assert page.headers["etag"]
            assert page.json()["items"][0]["id"] == listing_id

            detail = client.get(f"/api/v1/listings/{listing_id}")
            assert detail.status_code == 200
            cached = client.get(
                f"/api/v1/listings/{listing_id}",
                headers={"If-None-Match": detail.headers["etag"]},
            )
            assert cached.status_code == 304

            changed = client.post(
                f"/api/v1/listings/{listing_id}/inventory",
                json={
                    "quantity_delta": "-3",
                    "movement_type": "adjustment",
                    "reason": "Market sale",
                },
            )
            assert changed.status_code == 200
            assert changed.json()["available_quantity"] == "7.000"
            fresh = client.get(f"/api/v1/listings/{listing_id}")
            assert fresh.status_code == 200
            assert fresh.json()["available_quantity"] == "7.000"
            if TEST_REDIS_URL:
                assert fresh.headers["x-cache"] == "MISS"

            stale = client.patch(
                f"/api/v1/listings/{listing_id}",
                json={"expected_version": 1, "title": "Stale title"},
            )
            assert stale.status_code == 409
            assert stale.json()["error"]["code"] == "listing_version_conflict"

            assert (
                client.delete(
                    f"/api/v1/listings/{listing_id}/images/{image.json()['id']}"
                ).status_code
                == 204
            )
            assert (
                client.delete(
                    f"/api/v1/listings/{listing_id}", params={"expected_version": 3}
                ).status_code
                == 204
            )
    finally:
        if listing_id and product_id and category_id:
            asyncio.run(cleanup(listing_id, product_id, category_id))


@pytest.mark.anyio
async def test_concurrent_inventory_changes_cannot_oversell() -> None:
    assert TEST_DATABASE_URL is not None
    database = Database(Settings(environment="test", database_url=SecretStr(TEST_DATABASE_URL)))
    farmer_id, category_id, product_id, listing_id = (uuid4() for _ in range(4))
    actor = AuthenticatedUser(
        id=farmer_id,
        email="stock@example.test",
        phone_e164=None,
        roles=frozenset({"farmer"}),
        token_version=0,
    )
    try:
        async with database.session() as session:
            session.add(
                User(
                    id=farmer_id,
                    email=f"{farmer_id}@example.test",
                    password_hash="x",
                    status="active",
                )
            )
            session.add(UserRole(user_id=farmer_id, role_name="farmer"))
            await session.flush()
            session.add(
                ProduceCategory(id=category_id, name="Vegetables", slug=f"vegetables-{category_id}")
            )
            await session.flush()
            session.add(
                Product(
                    id=product_id,
                    category_id=category_id,
                    name="Cabbage",
                    slug=f"cabbage-{product_id}",
                    default_unit="kg",
                )
            )
            await session.flush()
            session.add(
                Listing(
                    id=listing_id,
                    farmer_id=farmer_id,
                    product_id=product_id,
                    title="Fresh cabbage",
                    price_amount=Decimal("80"),
                    currency="KES",
                    available_quantity=Decimal("10"),
                    quantity_unit="kg",
                    status="active",
                    version=1,
                )
            )
            await session.commit()

        async def reserve() -> object:
            async with database.session() as session:
                return await CatalogService(CatalogRepository(session)).change_inventory(
                    actor, listing_id, Decimal("-7"), "adjustment", "Concurrent sale test"
                )

        results = await asyncio.gather(reserve(), reserve(), return_exceptions=True)
        assert sum(not isinstance(result, Exception) for result in results) == 1
        failure = next(result for result in results if isinstance(result, Exception))
        assert isinstance(failure, ApiError)
        assert failure.code == "insufficient_inventory"

        async with database.session() as session:
            stored = await session.get(Listing, listing_id)
            assert stored is not None
            assert stored.available_quantity == Decimal("3.000")
            movements = list(
                await session.scalars(
                    select(InventoryMovement).where(InventoryMovement.listing_id == listing_id)
                )
            )
            assert len(movements) == 1
            assert movements[0].resulting_quantity == Decimal("3.000")
    finally:
        async with database.session() as session:
            await session.execute(
                delete(InventoryMovement).where(InventoryMovement.listing_id == listing_id)
            )
            await session.execute(delete(Listing).where(Listing.id == listing_id))
            await session.execute(delete(Product).where(Product.id == product_id))
            await session.execute(delete(ProduceCategory).where(ProduceCategory.id == category_id))
            await session.execute(delete(User).where(User.id == farmer_id))
            await session.commit()
        await database.dispose()


@pytest.mark.anyio
async def test_optimistic_listing_updates_allow_only_one_writer() -> None:
    assert TEST_DATABASE_URL is not None
    database = Database(Settings(environment="test", database_url=SecretStr(TEST_DATABASE_URL)))
    farmer_id, category_id, product_id, listing_id = (uuid4() for _ in range(4))
    actor = AuthenticatedUser(farmer_id, "version@example.test", None, frozenset({"farmer"}), 0)
    try:
        async with database.session() as session:
            session.add(
                User(
                    id=farmer_id,
                    email=f"{farmer_id}@example.test",
                    password_hash="x",
                    status="active",
                )
            )
            session.add(UserRole(user_id=farmer_id, role_name="farmer"))
            await session.flush()
            session.add(ProduceCategory(id=category_id, name="Fruit", slug=f"fruit-{category_id}"))
            await session.flush()
            session.add(
                Product(
                    id=product_id,
                    category_id=category_id,
                    name="Mango",
                    slug=f"mango-{product_id}",
                    default_unit="kg",
                )
            )
            await session.flush()
            session.add(
                Listing(
                    id=listing_id,
                    farmer_id=farmer_id,
                    product_id=product_id,
                    title="Mangoes",
                    price_amount=Decimal("120"),
                    currency="KES",
                    available_quantity=Decimal("20"),
                    quantity_unit="kg",
                    status="active",
                    version=1,
                )
            )
            await session.commit()

        async def rename(title: str) -> object:
            async with database.session() as session:
                return await CatalogService(CatalogRepository(session)).update_listing(
                    actor, listing_id, ListingUpdate(expected_version=1, title=title)
                )

        results = await asyncio.gather(
            rename("Mangoes A"), rename("Mangoes B"), return_exceptions=True
        )
        assert sum(not isinstance(result, Exception) for result in results) == 1
        conflict = next(result for result in results if isinstance(result, Exception))
        assert isinstance(conflict, ApiError)
        assert conflict.code == "listing_version_conflict"
        async with database.session() as session:
            stored = await session.get(Listing, listing_id)
            assert stored is not None and stored.version == 2
    finally:
        async with database.session() as session:
            await session.execute(delete(Listing).where(Listing.id == listing_id))
            await session.execute(delete(Product).where(Product.id == product_id))
            await session.execute(delete(ProduceCategory).where(ProduceCategory.id == category_id))
            await session.execute(delete(User).where(User.id == farmer_id))
            await session.commit()
        await database.dispose()
