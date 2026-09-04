from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any, TypeVar

from skill_runtime.errors import SkillTimeoutError

T = TypeVar("T")


def run_with_timeout(func: Callable[..., T], args: tuple[Any, ...] = (), kwargs: dict[str, Any] | None = None, timeout_seconds: int = 30) -> T:
    kwargs = kwargs or {}
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout_seconds)
        except FuturesTimeout as exc:
            future.cancel()
            raise SkillTimeoutError(f"skill exceeded timeout of {timeout_seconds}s") from exc
