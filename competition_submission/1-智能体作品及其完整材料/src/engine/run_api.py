"""Uvicorn entry point that configures the Redis broker before importing actors."""

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from engine.settings import settings

dramatiq.set_broker(RedisBroker(url=settings.redis_url))

from engine.api import app  # noqa: E402

__all__ = ["app"]
