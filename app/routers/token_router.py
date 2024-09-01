import asyncio
from contextlib import asynccontextmanager
from redis import asyncio as aioredis
from fastapi import APIRouter, HTTPException, FastAPI
from fastapi.params import Depends

from app.schema.token import Token
from app.services.token_service import TokenService
from app.utils.redis import get_redis_client
from app.logger import logger

router = APIRouter(prefix="/token",
                   tags = ["tokens"])

def get_token_service(redis_client:aioredis.Redis = Depends(get_redis_client)) -> TokenService:
    return TokenService(redis_client)


@router.post("/generateToken")
async def generate_new_token(token_service:TokenService = Depends(get_token_service)):
    logger.info("Generate Token Called")

    try:
        return await token_service.generate_token()
    except Exception as e:
        logger.error(f"Error in generating token: {e}")
        raise HTTPException(status_code=400,detail=str(e))



@router.get("/acquireToken", response_model=Token)
async def get_new_token(token_service:TokenService = Depends(get_token_service)) -> Token:
    logger.info("Acquire Token Called")

    try:
         return await token_service.assign_token()
    except Exception as e:
        logger.error(f"Error in acquiring token: {e}")
        raise HTTPException(status_code=400,detail=str(e))


@router.put("/keepAlive")
async def keep_token_alive(token:Token,token_service:TokenService = Depends(get_token_service)):
    logger.info(f"Keep Alive Called for {token.token}")
    try:
        await token_service.keep_alive(str(token.token))
        logger.info(f"Keep Alive Signal Sent for {token.token}")
        return f"Token {token} has received keep alive signal"
    except Exception as e:
        logger.error(f"Error in keep alive: {e}")
        raise HTTPException(status_code=400,detail=str(e))


@router.put("/unblockToken")
async def unblock_given_token(token:Token,token_service:TokenService = Depends(get_token_service)):
    logger.info(f"Unblock Token Called for {token.token}")
    try:
        return await token_service.unblock_token(str(token.token))
    except Exception as e:
        logger.error(f"Error in unblock token: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/deleteToken")
async def delete_given_token(token:Token,token_service:TokenService = Depends(get_token_service)):
    logger.info(f"Delete Token Called for {token.token}")
    try:
        return await token_service.delete_token(str(token.token))
    except Exception as e:
        logger.error(f"Error in delete token: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@asynccontextmanager
async def lifespan(app:FastAPI):
    async for redis_client in get_redis_client():
        token_service = TokenService(redis_client)
        logger.info("Starting monitoring")
        task = asyncio.create_task(token_service.monitor_expired_tokens())
        try:
            yield
        finally:
            task.cancel()
            await task
