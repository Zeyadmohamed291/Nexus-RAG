import asyncio
import concurrent.futures

def safe_async_run(coro):
    """
    Run an async coroutine safely, whether called from an existing event loop thread
    (e.g., inside FastAPI request handler) or from a separate worker thread.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(lambda: asyncio.run(coro)).result()
    else:
        return asyncio.run(coro)
