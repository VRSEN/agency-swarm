import asyncio


def run_async_sync(async_fn, *args, **kwargs):
    """Run an async function synchronously."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        raise RuntimeError("run_async_sync cannot be called from a running event loop")

    return asyncio.run(async_fn(*args, **kwargs))
