import redis
from app.core.config import settings


# Create a global Redis client using the configured URL
# decode_responses=True returns str instead of bytes
redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
