"""
Export the OpenAPI document without running a server.

    python scripts/export_openapi.py [output-path]

Default output: ../frontend/lib/api/openapi.json (committed; the frontend
generates its TypeScript types from it so Vercel builds need no backend).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("MARKET_AUTOSTART", "false")
os.environ.setdefault("ENVIRONMENT", "test")

from algoviz.main import create_app

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "api" / "openapi.json"


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    spec = create_app().openapi()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(spec['paths'])} paths, {len(spec['components']['schemas'])} schemas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
