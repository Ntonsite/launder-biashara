"""Fixed-window counters. Redis is used when REDIS_URL is reachable so limits hold across API replicas;
otherwise an in-process store is used (fine for a single dev process, documented as such)."""
import logging
import threading
import time

from .config import settings

log = logging.getLogger("launder.ratelimit")


class _MemoryStore:
    def __init__(self):
        self._data: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def incr(self, key: str, window: int) -> int:
        now = time.monotonic()
        with self._lock:
            count, expires = self._data.get(key, (0, now + window))
            if expires <= now:
                count, expires = 0, now + window
            count += 1
            self._data[key] = (count, expires)
            return count

    def get(self, key: str) -> int:
        with self._lock:
            count, expires = self._data.get(key, (0, 0))
            return count if expires > time.monotonic() else 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


class _RedisStore:
    def __init__(self, client):
        self.client = client

    def incr(self, key: str, window: int) -> int:
        pipe = self.client.pipeline()
        pipe.incr(key)
        pipe.expire(key, window, nx=True)
        return int(pipe.execute()[0])

    def get(self, key: str) -> int:
        return int(self.client.get(key) or 0)

    def reset(self, key: str) -> None:
        self.client.delete(key)

    def clear(self) -> None:
        pass


def _build_store():
    if settings.redis_url:
        try:
            import redis

            client = redis.Redis.from_url(settings.redis_url, socket_timeout=1)
            client.ping()
            return _RedisStore(client)
        except Exception as exc:  # degrade, never take the API down because Redis is unavailable
            log.warning("redis_unavailable_using_memory", extra={"error": str(exc)})
    return _MemoryStore()


store = _build_store()


def backend_name() -> str:
    return "redis" if isinstance(store, _RedisStore) else "memory"


def hit(key: str, window: int) -> int:
    return store.incr(f"rl:{key}", window)


def count(key: str) -> int:
    return store.get(f"rl:{key}")


def reset(key: str) -> None:
    store.reset(f"rl:{key}")
