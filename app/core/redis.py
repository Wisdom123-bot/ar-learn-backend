import os
import redis
import json
import logging
from typing import Optional, Any
from functools import wraps

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL")

def _get_tls_redis_url(url: str) -> str:
    """
    Upstash Redis requires TLS. Ensure the URL uses rediss:// scheme.
    Handles cases where the env var is mistakenly set to redis://.
    """
    if url.startswith("redis://"):
        return url.replace("redis://", "rediss://", 1)
    return url

def _create_redis_client():
    if not REDIS_URL:
        logger.warning("REDIS_URL not found. Caching will be disabled.")
        return None
    try:
        tls_url = _get_tls_redis_url(REDIS_URL)
        return redis.from_url(
            tls_url,
            decode_responses=True,
            socket_keepalive=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            ssl_cert_reqs=None,  # Upstash uses self-signed-friendly TLS
        )
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {str(e)}")
        return None

redis_client = _create_redis_client()

def cache_result(expire: int = 60, prefix: str = "cache"):
    """
    Simple decorator to cache function results in Redis.
    Defaults to 60 seconds.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not redis_client:
                return await func(*args, **kwargs)

            # Create a cache key based on function name and arguments
            key = f"{prefix}:{func.__name__}:{str(args)}:{str(kwargs)}"
            
            try:
                cached = redis_client.get(key)
                if cached:
                    return json.loads(cached)
            except Exception as e:
                logger.error(f"Redis get error: {str(e)}")

            # Execute the actual function
            result = await func(*args, **kwargs)

            try:
                redis_client.setex(key, expire, json.dumps(result))
            except Exception as e:
                logger.error(f"Redis set error: {str(e)}")

            return result
        return wrapper
    return decorator

def get_redis():
    """Dependency for FastAPI routes to access Redis directly."""
    return redis_client