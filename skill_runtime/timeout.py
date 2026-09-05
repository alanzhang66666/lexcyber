from __future__ import annotations

import multiprocessing
import pickle
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any, Callable, TypeVar

from skill_runtime.errors import SkillHandlerError, SkillTimeoutError

T = TypeVar("T")


def _child(queue: Any, func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
    try:
        queue.put(("ok", func(*args, **kwargs)))
    except BaseException as exc:  # serialize only the safe error text across the process boundary
        queue.put(("error", exc.__class__.__name__, str(exc)))


def _thread_fallback(func: Callable[..., T], args: tuple[Any, ...], kwargs: dict[str, Any], timeout_seconds: int) -> T:
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(func, *args, **kwargs)
    try:
        result = future.result(timeout=timeout_seconds)
        pool.shutdown(wait=True)
        return result
    except FuturesTimeout as exc:
        future.cancel()
        pool.shutdown(wait=False, cancel_futures=True)
        raise SkillTimeoutError(f"skill exceeded timeout of {timeout_seconds}s") from exc


def run_with_timeout(func: Callable[..., T], args: tuple[Any, ...] = (), kwargs: dict[str, Any] | None = None, timeout_seconds: int = 30) -> T:
    """Run registered handlers in a killable process; retain a thread fallback for non-picklable test callables."""
    kwargs = kwargs or {}
    try:
        pickle.dumps((func, args, kwargs))
    except (pickle.PickleError, TypeError, AttributeError):
        return _thread_fallback(func, args, kwargs, timeout_seconds)

    ctx = multiprocessing.get_context("spawn")
    queue = ctx.Queue(maxsize=1)
    process = ctx.Process(target=_child, args=(queue, func, args, kwargs), daemon=True)
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(2)
        if process.is_alive() and hasattr(process, "kill"):
            process.kill()
            process.join(2)
        queue.close()
        raise SkillTimeoutError(f"skill exceeded timeout of {timeout_seconds}s")
    try:
        message = queue.get(timeout=1)
    except Exception as exc:
        queue.close()
        raise SkillHandlerError("skill process exited without a result") from exc
    finally:
        queue.close()
    if message[0] == "ok":
        return message[1]
    raise SkillHandlerError(f"{message[1]}: {message[2]}")
