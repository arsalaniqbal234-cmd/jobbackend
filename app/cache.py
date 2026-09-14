import hashlib
import json
import logging
import os
import time
import uuid
from functools import lru_cache

import redis

from app.config import integer_env

logger = logging.getLogger(__name__)
_failure_until = 0.0


@lru_cache(maxsize=1)
def client():
    url = os.getenv("REDIS_URL")
    return redis.Redis.from_url(
        url, decode_responses=True, socket_connect_timeout=0.2, socket_timeout=0.2
    ) if url else None


def available():
    return client() is not None and time.monotonic() >= _failure_until


def failed():
    global _failure_until
    _failure_until = time.monotonic() + 5
    logger.warning("Search cache unavailable; serving database results")


def get_or_load(params: dict, loader):
    if not available():
        return loader(), "BYPASS"
    try:
        client().set("rozgar:jobs:version", uuid.uuid4().hex, nx=True)
        version = client().get("rozgar:jobs:version")
        if version is None:
            return loader(), "BYPASS"
        key = "rozgar:jobs:" + version + ":" + hashlib.sha256(
            json.dumps(params, sort_keys=True).encode()
        ).hexdigest()
        cached = client().get(key)
        if cached:
            return json.loads(cached), "HIT"
    except (redis.RedisError, ValueError):
        failed()
        return loader(), "BYPASS"
    result = loader()
    try:
        client().setex(key, integer_env("CACHE_TTL_SECONDS", 60), json.dumps(result))
    except redis.RedisError:
        failed()
    return result, "MISS"


def invalidate_jobs():
    if client() is not None:
        try:
            client().set("rozgar:jobs:version", uuid.uuid4().hex)
        except redis.RedisError:
            failed()  # Any old entries still expire at the configured TTL.
