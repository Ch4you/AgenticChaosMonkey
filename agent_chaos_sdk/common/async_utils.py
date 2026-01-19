"""
Async utilities for offloading CPU-bound work.
"""

import asyncio
import functools
from typing import Any, Callable


async def run_cpu_bound(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """
    Run a CPU-bound function in the default executor.
    """
    loop = asyncio.get_running_loop()
    if kwargs:
        bound = functools.partial(func, *args, **kwargs)
        return await loop.run_in_executor(None, bound)
    return await loop.run_in_executor(None, func, *args)
