"""
ARPS — Lightweight in-process cache for expensive aggregate queries
(dashboard statistics, counts, CGPA summaries, etc.)

Why not Flask-Caching / Redis?
This app runs as a single-process Flask app on modest university
infrastructure. A tiny thread-safe TTL dict cache gives the same
practical benefit (avoids re-running heavy aggregate/COUNT queries
on every page load) without adding an external dependency or moving
part of the infrastructure needed and increasing complexity. If the
app is ever deployed with multiple worker processes behind a load
balancer, swap this module's internals for Flask-Caching backed by
Redis/Memcached — the `cached()` / `invalidate()` call sites in the
routes will not need to change.
"""
import time
import threading
import functools

_lock = threading.Lock()
_store: dict[str, tuple[float, object]] = {}   # key -> (expires_at, value)

DEFAULT_TTL = 60  # seconds


def cache_get(key: str):
    with _lock:
        entry = _store.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if time.time() > expires_at:
            _store.pop(key, None)
            return None
        return value


def cache_set(key: str, value, ttl: int = DEFAULT_TTL):
    with _lock:
        _store[key] = (time.time() + ttl, value)


def cache_delete(key: str):
    with _lock:
        _store.pop(key, None)


def invalidate(prefix: str):
    """Remove every cached entry whose key starts with `prefix`.
    Call this after any write that would make a cached value stale
    (e.g. a score is entered, a student is edited, results are published).
    """
    with _lock:
        for k in [k for k in _store if k.startswith(prefix)]:
            _store.pop(k, None)


def clear_all():
    with _lock:
        _store.clear()


def cached(key_fn=None, ttl: int = DEFAULT_TTL):
    """Decorator that caches a function's return value.

    key_fn: optional callable(*args, **kwargs) -> str suffix appended to the
            function's qualified name to build the cache key. Use this to
            vary the cache per-argument (e.g. per student_id, per session).
            If omitted, the function is cached globally (no args vary it).
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            suffix = key_fn(*args, **kwargs) if key_fn else ""
            key = f"{fn.__module__}.{fn.__qualname__}:{suffix}"
            hit = cache_get(key)
            if hit is not None:
                return hit
            value = fn(*args, **kwargs)
            cache_set(key, value, ttl)
            return value
        wrapper.cache_key_prefix = f"{fn.__module__}.{fn.__qualname__}"
        return wrapper
    return decorator
