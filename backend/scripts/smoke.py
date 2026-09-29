from __future__ import annotations

import argparse
import json
import urllib.request


def fetch(base_url: str, path: str) -> dict[str, object]:
    request = urllib.request.Request(f"{base_url.rstrip('/')}{path}", method="GET")
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
        if response.status != 200:
            raise RuntimeError(f"{path} returned HTTP {response.status}")
        return json.loads(response.read())


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test a deployed Mavuno API")
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    if fetch(args.base_url, "/health/live") != {"status": "alive"}:
        raise RuntimeError("liveness response is invalid")
    if fetch(args.base_url, "/health/ready") != {"status": "ready"}:
        raise RuntimeError("readiness response is invalid")
    contract = fetch(args.base_url, "/openapi.json")
    required_paths = {
        "/api/v1/auth/login",
        "/api/v1/listings",
        "/api/v1/orders",
        "/api/v1/payments",
        "/api/v1/conversations",
        "/api/v1/premium/subscriptions",
    }
    missing = required_paths.difference(contract.get("paths", {}))
    if missing:
        raise RuntimeError(f"OpenAPI contract is missing: {', '.join(sorted(missing))}")


if __name__ == "__main__":
    main()
