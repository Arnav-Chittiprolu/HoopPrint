from __future__ import annotations

from app.services.rate_limit import InFlightSet, SlidingWindowLimiter


def test_sliding_window_allows_then_blocks():
    limiter = SlidingWindowLimiter(limit=2, window_s=10)
    assert limiter.allow("u", now=1.0)[0] is True
    assert limiter.allow("u", now=2.0)[0] is True
    allowed, retry = limiter.allow("u", now=3.0)
    assert allowed is False
    assert retry >= 1


def test_sliding_window_expires():
    limiter = SlidingWindowLimiter(limit=1, window_s=5)
    assert limiter.allow("u", now=0.0)[0] is True
    assert limiter.allow("u", now=4.0)[0] is False
    assert limiter.allow("u", now=5.1)[0] is True


def test_inflight_is_idempotent():
    lock = InFlightSet()
    assert lock.acquire("a") is True
    assert lock.acquire("a") is False
    assert lock.contains("a") is True
    lock.release("a")
    assert lock.acquire("a") is True
