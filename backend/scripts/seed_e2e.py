"""
Seed the end-to-end database
============================

    python scripts/seed_e2e.py --db data/e2e.db --models data/e2e_models

Gives every Playwright run the same starting point: 30 minutes of synthetic
history (fixed seed, run through the real engine so bars carry every feature,
the volatility state and the trend) and a model trained on it. The first run
builds a template under `data/e2e-seed/`; every run then replaces the target
database and model store with a fresh copy of it, so runs never inherit each
other's rows and the Intelligence page has a model from the first second.

The template is rebuilt when this script's `SEED_VERSION`, the migration head
or the model manifest changes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("MARKET_AUTOSTART", "false")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from alembic.script import ScriptDirectory  # noqa: E402
from sqlalchemy import insert  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from algoviz.config import Settings  # noqa: E402
from algoviz.core.workers import run_in_thread  # noqa: E402
from algoviz.db import _alembic_config, create_engine_from_settings, run_migrations  # noqa: E402
from algoviz.market.bars import Bar  # noqa: E402
from algoviz.market.persistence import BarCollector, bar_to_row  # noqa: E402
from algoviz.market.service import SymbolEngine  # noqa: E402
from algoviz.market.synthetic import SyntheticSource  # noqa: E402
from algoviz.ml.engine import MLEngine  # noqa: E402
from algoviz.ml.registry import model_manifest  # noqa: E402
from algoviz.models import MarketSnapshot  # noqa: E402
from algoviz.ws.hub import Hub  # noqa: E402

SEED_VERSION = 1
SYMBOL = "BTCUSDT"
N_BARS = 1_800
SEED = 7
START_MS = 1_790_000_000_000  # fixed, so the template is byte-for-byte the same on every machine
TEMPLATE = BACKEND / "data" / "e2e-seed"


def _cfg(db: Path, models: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        DATA_SOURCE="synthetic",
        DATABASE_URL=f"sqlite+aiosqlite:///{db.as_posix()}",
        ML_MODEL_DIR=models,
        ML_MIN_DATA_POINTS=300,
    )


def _stamp(cfg: Settings) -> dict[str, Any]:
    head = ScriptDirectory.from_config(_alembic_config(cfg.DATABASE_URL)).get_current_head()
    manifest = model_manifest(
        cfg.ML_HORIZON_S, cfg.ML_HORIZON_S, cfg.ML_BARRIER_K, cfg.ML_MIN_BARRIER_BPS
    )
    return {
        "version": SEED_VERSION,
        "bars": N_BARS,
        "seed": SEED,
        "migration": head,
        "manifest": manifest,
    }


async def _history(cfg: Settings) -> list[Bar]:
    writer = BarCollector()
    src = SyntheticSource(SYMBOL, seed=SEED, speed=0, start_ms=START_MS)
    engine = SymbolEngine(
        SYMBOL,
        cfg,
        src,
        Hub(),
        writer=writer,
        preload=False,
        intelligence=False,
        offload=run_in_thread,
    )
    await engine.start()
    try:
        while len(writer.bars) < N_BARS:  # noqa: ASYNC110 — polling a counter
            await asyncio.sleep(0.05)
    finally:
        await engine.stop()
    return writer.bars[:N_BARS]


async def _build(cfg: Settings, db: Path) -> None:
    await asyncio.to_thread(run_migrations, cfg.DATABASE_URL)  # Alembic runs its own loop
    bars = await _history(cfg)
    eng = create_engine_from_settings(cfg.DATABASE_URL)
    sf = async_sessionmaker(eng, expire_on_commit=False)
    async with sf() as session:
        await session.execute(insert(MarketSnapshot), [bar_to_row(b) for b in bars])
        await session.commit()
    ml = MLEngine(SYMBOL, cfg, sf, persist=False, offload=run_in_thread)
    await ml.start(history=bars)
    while not ml.ready:  # noqa: ASYNC110 — the first training run, in a thread
        await asyncio.sleep(0.2)
    await ml.stop()
    await eng.dispose()
    print(f"seeded {len(bars)} bars and model v{ml.version} ({ml.samples} samples) into {db}")


def _copy(template_db: Path, template_models: Path, db: Path, models: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        Path(f"{db}{suffix}").unlink(missing_ok=True)
    db.parent.mkdir(parents=True, exist_ok=True)
    src, dst = sqlite3.connect(template_db), sqlite3.connect(db)
    src.backup(dst)
    # the registry rows point at the template's artefacts: repoint them at the copy
    dst.execute(
        "update ml_models set file_path = replace(file_path, ?, ?)",
        (str(template_models), str(models)),
    )
    dst.commit()
    src.close()
    dst.close()
    shutil.rmtree(models, ignore_errors=True)
    shutil.copytree(template_models, models)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--models", type=Path, required=True)
    args = ap.parse_args()
    db, models = (BACKEND / args.db).resolve(), (BACKEND / args.models).resolve()

    template_db, template_models = TEMPLATE / "algoviz.db", TEMPLATE / "models"
    cfg = _cfg(template_db, template_models)
    stamp_file = TEMPLATE / "seed.json"
    stamp = _stamp(cfg)
    if not (
        stamp_file.exists() and json.loads(stamp_file.read_text()) == stamp and template_db.exists()
    ):
        shutil.rmtree(TEMPLATE, ignore_errors=True)
        TEMPLATE.mkdir(parents=True)
        asyncio.run(_build(cfg, template_db))
        stamp_file.write_text(json.dumps(stamp, indent=2))
    _copy(template_db, template_models, db, models)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
