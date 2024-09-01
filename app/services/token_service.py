"""
Functions for managing tokens in the system.
Functions:
    generate_token: Generates a new token.
    assign_token: Assigns a new token to a user.
    keep_alive: Extends the lifetime of a token.
    unblock_token: Unblocks an assigned token.
    delete_token: Deletes a token from the system.
    monitor_expired_tokens: Monitors the Redis database for expired tokens and takes appropriate action.
"""
import asyncio
from redis import asyncio as aioredis
from app.logger import logger
from app.config import settings
import uuid


class TokenService:
    def __init__(self, redis_client):
        self.redis_client = redis_client
    async def generate_token(self):
        """
        Generates a new token by creating a UUID, and storing it in Redis with
        two keys: one for the token itself and one for the token in the
        'Unassigned' set. The token is also added to the 'Token' set.

        The token is given a TTL in Redis, which is the length of time the
        token will be valid. This is set to the value of settings.token_expiry.

        Returns:
            None
        """
        while True:
            token = str(uuid.uuid4())
            token_key = f"token:{token}"
            if not await self.redis_client.sismember("Token", token_key):

                logger.info(f"Token: {token} generated")

                await self.redis_client.sadd("Unassigned",token_key)
                await self.redis_client.sadd("Token", token_key)

                await self.redis_client.setex(f"{token_key}:unassigned", settings.token_expiry, "active")
                await self.redis_client.setex(f"{token_key}:tokens",settings.token_expiry,"active")

                logger.info(f"Token: {token} added to Redis with expiry {settings.token_expiry}")

                return "token successfully generated"
            else:
                logger.info("Token already exists generating new token ........")

    async def assign_token(self):
        """
        Assigns a new token to a user.

        Returns:
            A dictionary containing the token.
        """
        token_key = await self.redis_client.spop("Unassigned")
        if token_key is None:
            logger.error("No available tokens")
            raise Exception("No available tokens")

        logger.info(f"Assigning Token {token_key}")
        assigned_key = f"{token_key}:assigned"
        await self.redis_client.sadd("Assigned",token_key)
        await self.redis_client.setex(assigned_key, settings.active_expiry, "active")

        await self.redis_client.delete(f"{token_key}:unassigned")
        logger.info(f"Removed token {token_key} from Unassigned")
        token = token_key.split(":")[1]

        return {"token":token}

    async def keep_alive(self,token:str):
        """
        Extends the lifetime of a token.

        Args:
            token (str): The token to be extended.

        Returns:
            None
        """
        token_key = f"token:{token}"
        if await self.redis_client.sismember("Token",token_key):
            if await self.redis_client.sismember("Assigned",token_key):
                assigned_key = f"{token_key}:assigned"
                current_ttl = await self.redis_client.ttl(assigned_key)
                await self.redis_client.expire(assigned_key,current_ttl+settings.keep_alive_interval)
                logger.info(
                    f"""Token {token} has current assigned ttl {current_ttl}, 
                                   changing assigned ttl to {current_ttl + settings.keep_alive_interval}"""
                )
            elif await self.redis_client.sismember("Unassigned",token_key):
                unassigned_key = f"{token_key}:unassigned"
                current_ttl = await self.redis_client.ttl(unassigned_key)

                await self.redis_client.expire(unassigned_key,current_ttl+settings.keep_alive_interval)
                logger.info(
                    f"""Token {token} has current unassigned ttl {current_ttl}, 
                                   changing unassigned ttl to {current_ttl + settings.keep_alive_interval}"""
                )
            tokens_key = f"{token_key}:tokens"
            current_ttl = await self.redis_client.ttl(tokens_key)
            await self.redis_client.expire(tokens_key,current_ttl+settings.keep_alive_interval)
            logger.info(
                f"""Token {token} has current token ttl {current_ttl}, 
                               changing token ttl to {current_ttl + settings.keep_alive_interval}"""
            )
        else:
            logger.error("No such token found")
            raise Exception("No such token found")

    async def unblock_token(self,token:str):
        """
        Unblocks an assigned token.

        Args:
            token (str): The token to be unblocked.

        Returns:
            str: A success message indicating that the token has been unblocked.
        """
        token_key = f"token:{token}"
        if not await self.redis_client.sismember("Token",token_key):
            logger.error(f"No such token present: {token}")
            raise Exception("No such token present")
        if not await self.redis_client.sismember("Assigned", token_key):
            logger.error(f"{token} is not assigned")
            raise Exception("This token is not assigned and hence cannot be unblocked")
        try:
            assigned_key = f"{token_key}:assigned"
            tokens_key = f"{token_key}:tokens"
            unassigned_key = f"{token_key}:unassigned"
            await self.redis_client.srem("Assigned",token_key)
            await self.redis_client.delete(assigned_key)
            ttl = await self.redis_client.ttl(tokens_key)
            logger.info(f"Acquired ttl is {ttl}")
            await self.redis_client.sadd("Unassigned", token_key)
            await self.redis_client.setex(unassigned_key,ttl,"active")
            logger.info(f"Token {token} has been unblocked with ttl {ttl}")
            return f"{token} has been unblocked"
        except Exception as e:
            logger.error(f"Error in unblocking token: {e}")
            raise e

    async def delete_token(self,token:str):
        """
        Deletes a token from the system.


        Args:
            token (str): The token to be deleted.
        Returns:
            str: A success message indicating that the token has been deleted.
        """
        token_key =f"token:{token}"
        if await self.redis_client.sismember("Token",token_key):
            await self.redis_client.srem("Unassigned",token_key)
            await self.redis_client.srem("Assigned",token_key)
            await self.redis_client.srem("Token",token_key)
            await self.redis_client.delete(f"{token_key}:assigned")
            await self.redis_client.delete(f"{token_key}:unassigned")
            await self.redis_client.delete(f"{token_key}:tokens")
            logger.info(f"Token {token} has been deleted")
            return f"{token} has been deleted"
        else:
            logger.error(f"No such token in system: {token}")
            raise Exception("No such token in system")

    async def monitor_expired_tokens(self):
        """
        Monitors the Redis database for expired tokens and takes appropriate action.

        If an assigned token expires, it is moved to the unassigned list. If an unassigned token expires, it is deleted from the system.
        """
        try:
            logger.info("Monitoring now")
            pubsub = self.redis_client.pubsub()
            await pubsub.psubscribe("__keyevent@0__:expired")
            async for message in pubsub.listen():
                if asyncio.current_task().cancelled():
                    logger.info("Monitor expired tokens cancelled. Cleaning up .........")
                    break
                if message["type"] == 'pmessage':
                    expired_key = message["data"]
                    try:
                        if expired_key.endswith(":assigned"):
                            token_key = ":".join(expired_key.split(":")[:-1])
                            remaining_ttl = await self.redis_client.ttl(f"{token_key}:tokens")
                            await self.redis_client.sadd("Unassigned", token_key)
                            await self.redis_client.srem("Assigned",token_key)
                            await self.redis_client.delete(f"{token_key}:assigned")
                            await self.redis_client.setex(f"{token_key}:unassigned", remaining_ttl, "active")
                        elif expired_key.endswith(":tokens"):
                            token = expired_key.split(":")[1]
                            await self.delete_token(token)
                    except asyncio.CancelledError:
                        logger.info("Monitor expired tokens cancelled. Cleaning up .........")
                        break
        except asyncio.CancelledError:
            logger.info("Task was cancelled. Exiting Gracefully")
        except aioredis.ConnectionError:
            logger.info("Connection to Redis lost, retrying in 5 seconds...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.info(f"An unexpected error occurred: {e}")
            await asyncio.sleep(5)