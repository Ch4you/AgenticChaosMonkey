import asyncio
from typing import Any, Callable


async def run_cpu_bound(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """
    Run a CPU-bound function in a thread to avoid blocking the event loop.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, func, *args, **kwargs)
