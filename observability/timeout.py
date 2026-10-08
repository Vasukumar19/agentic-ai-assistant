"""Timeout helpers — single hanging call must not hang the agent."""

from __future__ import annotations

import concurrent.futures
from typing import Callable, Any


class TimeoutError(RuntimeError):
    pass


def run_with_timeout(func: Callable, timeout_s: float, *args, **kwargs) -> Any:
    """Run func with timeout. Raises TimeoutError (observability.errors.TIMEOUT_ERROR) on expiry."""
    if timeout_s is None or timeout_s <= 0:
        return func(*args, **kwargs)
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    fut = ex.submit(func, *args, **kwargs)
    try:
        return fut.result(timeout=timeout_s)
    except concurrent.futures.TimeoutError as e:
        fut.cancel()
        ex.shutdown(wait=False, cancel_futures=True)
        raise TimeoutError(f"operation timed out after {timeout_s}s") from e
    except BaseException:
        ex.shutdown(wait=True)
        raise
    else:
        ex.shutdown(wait=True)
