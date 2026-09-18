from __future__ import annotations

import json
from pathlib import Path

from mavuno.core.config import Settings
from mavuno.main import create_app


def test_checked_in_openapi_contract_matches_application() -> None:
    contract_path = Path(__file__).parent / "contracts" / "openapi.json"
    checked_in = json.loads(contract_path.read_text(encoding="utf-8"))

    assert checked_in == create_app(Settings(environment="test")).openapi()


def test_mobile_farmer_buyer_journey_remains_in_contract() -> None:
    contract_path = Path(__file__).parent / "contracts" / "openapi.json"
    paths = json.loads(contract_path.read_text(encoding="utf-8"))["paths"]
    journey = {
        ("/api/v1/auth/register", "post"),
        ("/api/v1/auth/login", "post"),
        ("/api/v1/listings", "get"),
        ("/api/v1/cart/items/{listing_id}", "put"),
        ("/api/v1/orders", "post"),
        ("/api/v1/payments", "post"),
        ("/api/v1/fulfilments/{order_id}/status", "post"),
        ("/api/v1/conversations/{conversation_id}/messages", "post"),
        ("/api/v1/premium/subscriptions", "post"),
        ("/api/v1/prebookings", "post"),
    }

    assert all(method in paths[path] for path, method in journey)
