"""Cache lifetime, expiry boundary and bounded-size tests."""

import pytest

from src.cache import TTLCache


def test_ttl_bound_and_clock() -> None:
    now = [0.0]
    cache = TTLCache[str, int](10, 2, lambda: now[0])
    cache.set("a", 1)
    cache.set("b", 2)
    assert cache.get("a") == 1
    cache.set("c", 3)
    assert cache.get("a") is None
    now[0] = 10
    assert cache.get("b") is None
    assert cache.get("c") is None
    cache.set("a", 4)
    cache.set("a", 5)
    assert cache.get("a") == 5


def test_disabled_and_invalid() -> None:
    cache = TTLCache[str, int](0)
    cache.set("a", 1)
    assert cache.get("a") is None
    with pytest.raises(ValueError):
        TTLCache(-1)
    with pytest.raises(ValueError):
        TTLCache(1, 0)
