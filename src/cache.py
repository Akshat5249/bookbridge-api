"""Small bounded in-process TTL cache with an injectable monotonic clock."""

from collections import OrderedDict
from collections.abc import Callable
from time import monotonic


class TTLCache[K, V]:
    """Cache successful values; evict expired entries and oldest insertions."""

    def __init__(
        self, ttl: float, max_size: int = 256, clock: Callable[[], float] = monotonic
    ) -> None:
        if ttl < 0 or max_size < 1:
            raise ValueError("TTL must be nonnegative and max_size positive")
        self.ttl, self.max_size, self.clock = ttl, max_size, clock
        self._items: OrderedDict[K, tuple[float, V]] = OrderedDict()

    def get(self, key: K) -> V | None:
        """Return a live value or remove an expired value."""
        item = self._items.get(key)
        if item is None:
            return None
        expires, value = item
        if self.clock() >= expires:
            del self._items[key]
            return None
        return value

    def set(self, key: K, value: V) -> None:
        """Store a successful value, bounded by max_size; zero TTL disables caching."""
        if not self.ttl:
            return
        now = self.clock()
        for expired in [k for k, (deadline, _) in self._items.items() if deadline <= now]:
            del self._items[expired]
        self._items.pop(key, None)
        self._items[key] = (now + self.ttl, value)
        while len(self._items) > self.max_size:
            self._items.popitem(last=False)
