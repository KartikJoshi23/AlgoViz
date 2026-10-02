"""
Worker isolation
================

CPU-heavy work never runs on the event loop.

- `InferenceWorker` — one dedicated thread per model for inference and SHAP.
  OpenMP is pinned to a single thread inside it: a one-row predict gains
  nothing from a parallel region, and under CPU contention that region's
  barrier is what froze the loop for seconds (v16, all cores busy: default
  threads p50 2.0 s / max 15 s; one thread p50 74 ms / max 134 ms). With
  libgomp (Linux) the limit is per thread; with MSVC's vcomp (Windows wheels)
  it is process-wide — harmless, because nothing else in the server process
  uses OpenMP once training and HMM fits run in their own processes.
- `run_isolated()` — runs a picklable function in a freshly **spawned**
  process (model training, HMM fitting) with capped BLAS/OpenMP threads and a
  hard timeout. The child shares neither the GIL nor the thread pools with the
  server, and exits afterwards so its memory goes back to the OS. On POSIX it
  also runs at a lower scheduling priority: on a single-CPU host (the hosted
  backend) a fit at equal priority would take half the core from the loop
  that carries the feed.
- `run_in_thread()` — the same call shape in a thread, for callers that are
  already off the server loop (the backtester's synthetic history generator).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import multiprocessing
import os
import traceback
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from multiprocessing.connection import Connection
from typing import Any, TypeVar

logger = logging.getLogger("algoviz.workers")

T = TypeVar("T")

# (fn, *args) → result, executed somewhere other than the event loop.
Offload = Callable[..., Awaitable[Any]]

_SPAWN = multiprocessing.get_context("spawn")
_JOIN_TIMEOUT_S = 5.0
_CHILD_NICENESS = 10  # POSIX nice increment for isolated work; the server keeps priority


class WorkerError(RuntimeError):
    """The isolated function raised; the message carries the child traceback."""


class WorkerTimeout(TimeoutError):
    """The isolated function exceeded its time budget and was terminated."""


def default_threads() -> int:
    """Half the cores (at least one): training must leave the server room to breathe."""
    return max(1, (os.cpu_count() or 2) // 2)


# ── Inference thread ──────────────────────────────────────────────


def _pin_openmp_to_one_thread() -> None:
    from threadpoolctl import threadpool_limits

    # Not a context manager on purpose: the limit lives as long as the thread.
    threadpool_limits(limits=1, user_api="openmp")


class InferenceWorker:
    """A single thread that owns every predict / explain call for one model."""

    def __init__(self, name: str) -> None:
        self._pool = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix=name, initializer=_pin_openmp_to_one_thread
        )

    async def run(self, fn: Callable[..., T], *args: Any) -> T:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._pool, partial(fn, *args))

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


# ── Spawned process ───────────────────────────────────────────────


def _child_main(
    conn: Connection, fn: Callable[..., Any], args: tuple[Any, ...], threads: int
) -> None:
    try:
        from threadpoolctl import threadpool_limits

        if hasattr(os, "nice"):  # POSIX only; Windows has no nice()
            os.nice(_CHILD_NICENESS)
        with threadpool_limits(limits=threads):
            result = fn(*args)
        conn.send((True, result))
    except BaseException as exc:
        conn.send((False, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"))
    finally:
        conn.close()


async def run_isolated(
    fn: Callable[..., T], *args: Any, timeout_s: float, threads: int | None = None
) -> T:
    """
    Run `fn(*args)` in a new spawned process and return its (pickled) result.

    Raises `WorkerTimeout` after `timeout_s` (the child is terminated) and
    `WorkerError` if the function raised. Cancelling the awaiting task also
    terminates the child.
    """
    recv_end, send_end = _SPAWN.Pipe(duplex=False)
    proc = _SPAWN.Process(
        target=_child_main,
        args=(send_end, fn, args, threads or default_threads()),
        name=f"algoviz-{getattr(fn, '__name__', 'worker')}",
        daemon=True,
    )
    # start() writes the pickled arguments (megabytes of training data) into the
    # child's pipe and blocks until the child — still importing numpy/sklearn —
    # has read them: seconds. That must not happen on the event loop.
    starting = asyncio.ensure_future(asyncio.to_thread(proc.start))
    try:
        await asyncio.shield(starting)
        send_end.close()  # the child owns the only writer now: EOF if it dies
        # asyncio.timeout(), not wait_for(): on Python 3.11 wait_for swallows a cancellation
        # that races with the result arriving (gh-86296), and a cancelled fit would install.
        async with asyncio.timeout(timeout_s):
            ok, payload = await asyncio.to_thread(recv_end.recv)
    except TimeoutError as exc:
        raise WorkerTimeout(f"{proc.name} exceeded {timeout_s:.0f}s") from exc
    except EOFError as exc:
        raise WorkerError(f"{proc.name} exited without a result (code {proc.exitcode})") from exc
    finally:
        # Also on cancellation mid-start: let the start finish, then reap the child.
        with contextlib.suppress(BaseException):
            await starting
        if proc.pid is not None:
            if proc.is_alive():
                proc.terminate()
            await asyncio.to_thread(proc.join, _JOIN_TIMEOUT_S)
        send_end.close()
        recv_end.close()
    if not ok:
        raise WorkerError(payload)
    return payload


async def run_in_thread(fn: Callable[..., T], *args: Any, **_: Any) -> T:
    """`Offload` that runs in a thread (for code that is already off the server loop)."""
    return await asyncio.to_thread(fn, *args)
