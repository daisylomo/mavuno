from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mavuno.core.config import Settings  # noqa: E402
from mavuno.main import create_app  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the deterministic Mavuno OpenAPI contract")
    parser.add_argument(
        "output", type=Path, nargs="?", default=Path("tests/contracts/openapi.json")
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    contract = create_app(Settings(environment="test")).openapi()
    args.output.write_text(
        json.dumps(contract, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
