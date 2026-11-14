"""Write docs/openapi.json from the gateway app, or with --check fail if it is stale."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from memorydock_core.config import Settings
from memorydock_gateway.app import create_app

OUT = Path(__file__).resolve().parent.parent / "docs" / "openapi.json"


def render() -> str:
    app = create_app(Settings(_env_file=None))
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if docs/openapi.json is stale")
    args = parser.parse_args(argv)
    text = render()
    if args.check:
        if not OUT.exists() or OUT.read_text() != text:
            print("docs/openapi.json is stale; run make openapi and commit the result")
            return 1
        print("docs/openapi.json is up to date")
        return 0
    OUT.write_text(text)
    print("wrote docs/openapi.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
