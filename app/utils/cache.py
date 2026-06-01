import json
import redis
from app.core.config import settings

# Try connecting to Redis; if it fails, cache is disabled gracefully
try:
    r = redis.from_url(settings.REDIS_URL, decode_responses=True)
    r.ping()
    redis_available = True
except Exception:
    r = None
    redis_available = False
    print("⚠️ Redis not available – caching disabled. Dashboards will query live.")


def get_cache(key: str):
    """Get a cached value as Python object (dict/list). Returns None if missing."""
    if not redis_available:
        return None
    try:
        data = r.get(key)
        if data:
            return json.loads(data)
    except Exception:
        pass
    return None


def set_cache(key: str, value, ttl: int = 300):
    """Set cache with TTL in seconds. value can be dict or list."""
    if not redis_available:
        return
    try:
        r.setex(key, ttl, json.dumps(value, default=str))
    except Exception:
        pass


def invalidate_cache(pattern: str = "*"):
    """Delete keys matching pattern. Use with caution."""
    if not redis_available:
        return
    try:
        keys = r.keys(pattern)
        if keys:
            r.delete(*keys)
    except Exception:
        pass