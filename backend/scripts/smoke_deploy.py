"""
Smoke-check a running deployment from the outside.

    python scripts/smoke_deploy.py https://algoviz-backend.onrender.com
    ADMIN_TOKEN=... python scripts/smoke_deploy.py <url> --with-token   # also a gated change

Checks what a visitor and the operator depend on: the deployed version is this
checkout's, the service is ready, reads are public and changes are gated (with
`--with-token`, a change made with the token from the environment is accepted
and deleted again), and CORS and the WebSocket admit the frontend origin but
not a foreign one. Exits 1 if any check fails.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any

import httpx
import websockets
from websockets.typing import Origin

from algoviz import __version__

FOREIGN_ORIGIN = "https://example.com"


class Checks:
    def __init__(self) -> None:
        self.failed: list[str] = []
        self.total = 0

    def __call__(self, ok: bool, what: str) -> None:
        self.total += 1
        if not ok:
            self.failed.append(what)
        print(("PASS " if ok else "FAIL ") + what)


async def _ws(base: str, origin: str) -> str:
    url = base.replace("http", "ws", 1) + "/ws"
    try:
        async with websockets.connect(url, origin=Origin(origin), open_timeout=30) as ws:
            first: dict[str, Any] = json.loads(await asyncio.wait_for(ws.recv(), 30))
            return f"open ({first.get('type')})"
    except websockets.exceptions.InvalidStatus as exc:
        return f"refused ({exc.response.status_code})"


async def smoke(base: str, origin: str, token: str | None) -> Checks:
    check = Checks()
    # a sleeping or cold-starting instance can take a minute to answer the first request
    async with httpx.AsyncClient(base_url=base, timeout=90) as c:
        version = (await c.get("/")).json().get("version")
        check(version == __version__, f"version {version} (this checkout: {__version__})")
        ready = await c.get("/health/ready")
        check(
            ready.status_code == 200,
            f"/health/ready {ready.status_code} {ready.json().get('checks')}",
        )
        access = (await c.get("/api/v1/auth/access")).json()
        check(access.get("writes_require_auth") is True, f"changes are gated: {access}")

        example = (await c.get("/api/v1/strategies/examples")).json()[0]
        body = {
            "name": "smoke check",
            "description": "smoke_deploy.py",
            "config": example["config"],
        }
        refused = await c.post("/api/v1/strategies", json=body)
        check(
            refused.status_code == 401
            and refused.headers["content-type"].startswith("application/problem+json"),
            f"a change without a token -> {refused.status_code} {refused.headers['content-type']}",
        )
        if token:
            auth = {"Authorization": f"Bearer {token}"}
            made = await c.post("/api/v1/strategies", json=body, headers=auth)
            check(made.status_code == 201, f"a change with the token -> {made.status_code}")
            if made.status_code == 201:
                gone = await c.delete(f"/api/v1/strategies/{made.json()['id']}", headers=auth)
                check(gone.status_code == 204, f"cleanup -> {gone.status_code}")

        for o, allowed in ((origin, True), (FOREIGN_ORIGIN, False)):
            pre = await c.options(
                "/api/v1/strategies",
                headers={
                    "Origin": o,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "authorization,content-type",
                },
            )
            granted = pre.headers.get("access-control-allow-origin") == o
            check(granted == allowed, f"CORS preflight from {o}: {pre.status_code}")

    for o, allowed in ((origin, True), (FOREIGN_ORIGIN, False)):
        state = await _ws(base, o)
        check(state.startswith("open") == allowed, f"WebSocket from {o}: {state}")
    return check


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("url", help="backend base URL, e.g. https://algoviz-backend.onrender.com")
    ap.add_argument(
        "--origin", default="https://algorithmic-viz.vercel.app", help="frontend origin"
    )
    ap.add_argument(
        "--with-token", action="store_true", help="also make a change with $ADMIN_TOKEN"
    )
    args = ap.parse_args()
    token = os.environ.get("ADMIN_TOKEN") if args.with_token else None
    if args.with_token and not token:
        ap.error("--with-token needs ADMIN_TOKEN in the environment")
    checks = asyncio.run(smoke(args.url.rstrip("/"), args.origin, token))
    print(f"\n{checks.total - len(checks.failed)}/{checks.total} passed")
    return 1 if checks.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
