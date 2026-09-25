import dramatiq
from dramatiq.brokers.redis import RedisBroker

from config.settings import settings


def configure_broker() -> RedisBroker:
    broker = RedisBroker(url=settings.redis_url)
    dramatiq.set_broker(broker)
    return broker
