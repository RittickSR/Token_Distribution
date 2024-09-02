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
        while True:                 # Loop until new token not present in redis is generated
            token = str(uuid.uuid4())
            token_key = f"token:{token}"
            if not await self.redis_client.sismember("Token", token_key):      # Check if token does not already exist

                logger.info(f"Token: {token} generated")

                await self.redis_client.sadd("Unassigned",token_key)          #Add token to unassigned set
                await self.redis_client.sadd("Token", token_key)              # Add token to token set

                await self.redis_client.setex(f"{token_key}:unassigned", settings.token_expiry, "active") #SET TTL
                await self.redis_client.setex(f"{token_key}:tokens",settings.token_expiry,"active") #SET TTL

                logger.info(f"Token: {token} added to Redis with expiry {settings.token_expiry}")

                return "token successfully generated"
            else:
                logger.info("Token already exists generating new token ........") #If token already exists, generate new

    async def assign_token(self, preset_token_key = None):
        """
        Assigns a new token to a user.

        Returns:
            A dictionary containing the token.
        """
        if not preset_token_key:
            token_key = await self.redis_client.spop("Unassigned")   #If a predetermined token has not been sent
        else:
            token_key = preset_token_key
            await self.redis_client.srem("Unassigned",token_key)    #Remove token from unassigned set if predetermined sent
        if token_key is None:
            logger.error("No available tokens")
            raise Exception("No available tokens")

        logger.info(f"Assigning Token {token_key}")
        assigned_key = f"{token_key}:assigned"
        await self.redis_client.sadd("Assigned",token_key)              #Add token to assigned set
        await self.redis_client.setex(assigned_key, settings.active_expiry, "active")  #Set assigned TTL

        await self.redis_client.delete(f"{token_key}:unassigned")        #Delete unassigned TTL
        logger.info(f"Removed token {token_key} from Unassigned")
        tokens_key = f"{token_key}:tokens"
        current_ttl = await self.redis_client.ttl(tokens_key)           #Get current token TTL
        if current_ttl < settings.active_expiry:
            await self.redis_client.expire(tokens_key, settings.active_expiry)      #If token expires before active expiry extend token expiry
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
        if await self.redis_client.sismember("Token",token_key):        #Check if token exists
            if await self.redis_client.sismember("Assigned",token_key):     #Check if token is assigned
                assigned_key = f"{token_key}:assigned"
                current_ttl = await self.redis_client.ttl(assigned_key)
                await self.redis_client.expire(assigned_key,current_ttl+settings.keep_alive_interval)  #Increase TTL
                logger.info(
                    f"""Token {token} has current assigned ttl {current_ttl}, 
                                   changing assigned ttl to {current_ttl + settings.keep_alive_interval}"""
                )
            elif await self.redis_client.sismember("Unassigned",token_key):  #Check if token is unassigned
                token = await self.assign_token(preset_token_key=token_key)  #Assign token and set new ttl
            tokens_key = f"{token_key}:tokens"
            current_ttl = await self.redis_client.ttl(tokens_key)
            await self.redis_client.expire(tokens_key,current_ttl+settings.keep_alive_interval)  #Add keep alive to overall token TTL
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
        if not await self.redis_client.sismember("Token",token_key):   #Check if token exists
            logger.error(f"No such token present: {token}")
            raise Exception("No such token present")
        if not await self.redis_client.sismember("Assigned", token_key):  #Check if token is assigned
            logger.error(f"{token} is not assigned")
            raise Exception("This token is not assigned and hence cannot be unblocked")
        try:
            assigned_key = f"{token_key}:assigned"
            tokens_key = f"{token_key}:tokens"
            unassigned_key = f"{token_key}:unassigned"
            await self.redis_client.srem("Assigned",token_key)          #Remove token from assigned set
            await self.redis_client.delete(assigned_key)                #Delete assigned TTL
            ttl = await self.redis_client.ttl(tokens_key)               #Get current token TTL
            logger.info(f"Acquired ttl is {ttl}")
            await self.redis_client.sadd("Unassigned", token_key)       #Add token to unassigned set
            await self.redis_client.setex(unassigned_key,ttl,"active")  #Set unassigned TTL
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
        if await self.redis_client.sismember("Token",token_key):        #Check if token exists
            await self.redis_client.srem("Unassigned",token_key)        #Remove token from unassigned set
            await self.redis_client.srem("Assigned",token_key)          #Remove token from assigned set
            await self.redis_client.srem("Token",token_key)             #Remove token from token set
            await self.redis_client.delete(f"{token_key}:assigned")     #Delete assigned TTL
            await self.redis_client.delete(f"{token_key}:unassigned")   #Delete unassigned TTL
            await self.redis_client.delete(f"{token_key}:tokens")       #Delete token TTL
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
            pubsub = self.redis_client.pubsub()                           #Create pubsub object
            await pubsub.psubscribe("__keyevent@0__:expired")
            async for message in pubsub.listen():                         #Listen for redis messages
                if asyncio.current_task().cancelled():                    #Handle exit gracefully
                    logger.info("Monitor expired tokens cancelled. Cleaning up .........")
                    break
                if message["type"] == 'pmessage':                         #Check if message is for subscribed topic
                    expired_key = message["data"]                         #Get expired key
                    try:
                        if expired_key.endswith(":assigned"):             #Check if assigned TTL is over
                            token_key = ":".join(expired_key.split(":")[:-1])
                            remaining_ttl = await self.redis_client.ttl(f"{token_key}:tokens")
                            if remaining_ttl < 0:
                                continue
                            await self.redis_client.sadd("Unassigned", token_key)   #Add token to unassigned set
                            await self.redis_client.srem("Assigned",token_key)      #Remove token from assigned set
                            await self.redis_client.delete(f"{token_key}:assigned") #Delete assigned TTL
                            await self.redis_client.setex(f"{token_key}:unassigned", remaining_ttl, "active")   #Set unassigned TTL
                        elif expired_key.endswith(":tokens"):               #Check if token TTL is over
                            token = expired_key.split(":")[1]
                            await self.delete_token(token)                    #Delete token
                    except asyncio.CancelledError:
                        logger.info("Monitor expired tokens cancelled. Cleaning up .........")
                        break
        except asyncio.CancelledError:
            logger.info("Task was cancelled. Exiting Gracefully")    #Gracefully exit if cancelled
        except aioredis.ConnectionError:
            logger.info("Connection to Redis lost, retrying in 5 seconds...")
            await asyncio.sleep(5)                                       #Sleep to avoid busywait
        except Exception as e:
            logger.info(f"An unexpected error occurred: {e}")
            await asyncio.sleep(5)                                       #Sleep to avoid busywait