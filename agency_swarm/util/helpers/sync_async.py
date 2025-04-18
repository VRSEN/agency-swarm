import asyncio

def run_async_sync(async_fn, *args, **kwargs):
    """
    Runs an async function synchronously, handling event loop logic.
    This is useful for wrapping async code in a sync interface.
    """
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            # If already in an event loop, create a new task and run it
            # This will block the current thread until the task is done
            # but is not ideal for nested event loops. For most agent use cases,
            # we assume sync context, so fallback to asyncio.run otherwise.
            return asyncio.run(async_fn(*args, **kwargs))
        else:
            return asyncio.run(async_fn(*args, **kwargs))
    except RuntimeError:
        # No event loop, safe to use asyncio.run
        return asyncio.run(async_fn(*args, **kwargs)) 