"""Shared provider helpers: errors and a small in-memory TTL cache."""
import time
from functools import wraps


class ProviderError(Exception):
    """A partner API failed or returned something unusable."""


class ProviderNotConfigured(ProviderError):
    """The affiliate keys for this provider are not set."""


def ttl_cache(seconds: int, max_items: int = 1000):
    """Cache an async function's results by its arguments.

    Saves partner API quota and LLM latency for popular searches. Swap for Redis when
    running more than one server process.
    """

    def decorator(fn):
        store: dict = {}

        @wraps(fn)
        async def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            hit = store.get(key)
            now = time.monotonic()
            if hit and hit[0] > now:
                return hit[1]
            value = await fn(*args, **kwargs)
            if len(store) >= max_items:
                store.clear()
            store[key] = (now + seconds, value)
            return value

        wrapper.cache_clear = store.clear
        return wrapper

    return decorator
