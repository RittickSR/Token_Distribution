from redis import asyncio as aioredis

from app.config import settings


# def get_redis_client(host:str,port:int) -> aioredis.Redis:
#     redis_client = aioredis.from_url(f"redis://{host}:{port}", decode_responses=True)
#     try:
#         yield redis_client
#     finally:
#         redis_client.close()


async def get_redis_client() -> aioredis.Redis:
    redis_client = aioredis.from_url(f"redis://{settings.redis_host}:{settings.redis_port}", decode_responses=True)
    try:
        yield redis_client
    finally:
        await redis_client.close()