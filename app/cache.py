import redis

redis_client = redis.Redis(
    host="redis",
    port=6379,
    decode_responses=True
)


def get_cache(key):
    return redis_client.get(key)


def set_cache(key, value):
    redis_client.set(key, value, ex=3600)


def delete_cache(key):
    redis_client.delete(key)