import uuid
from unittest.mock import patch, AsyncMock
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

generate_tokens_set = set()
assigned_tokens_set = set()
@pytest.fixture(scope="function", autouse=True)
def mock_redis_client():
    # Patch aioredis.from_url to return a mock Redis client
    with patch("app.utils.redis.aioredis.from_url") as mock_from_url:
        mock_redis_instance = AsyncMock()
        mock_from_url.return_value = mock_redis_instance
        async def mock_sismember(set_name, token):
            if set_name == "Token":
                # Differentiate between token sets for generation and deletion
                return token in generate_tokens_set
            if set_name == "Assigned":
                return token in assigned_tokens_set
            return False

        async def mock_spop(set_name):
            if set_name == "Unassigned":
                return generate_tokens_set.pop() if len(generate_tokens_set) else None
        # Mock all relevant Redis methods
        mock_redis_instance.sadd = AsyncMock(return_value=True)
        mock_redis_instance.setex = AsyncMock(return_value=True)
        mock_redis_instance.delete = AsyncMock(return_value=True)
        mock_redis_instance.srem = AsyncMock(return_value=True)
        mock_redis_instance.spop = AsyncMock(side_effect = mock_spop)
        mock_redis_instance.ttl = AsyncMock(return_value=3600)
        mock_redis_instance.sismember = AsyncMock(side_effect = mock_sismember) # or True based on your test scenario
        mock_redis_instance.pubsub = AsyncMock()
        mock_redis_instance.pubsub.return_value = AsyncMock()
        mock_redis_instance.pubsub.return_value.psubscribe = AsyncMock(return_value=None)
        mock_redis_instance.pubsub.return_value.listen = AsyncMock()
        mock_redis_instance.aclose = AsyncMock(return_value=None)

        yield mock_redis_instance

@pytest.mark.asyncio
async def test_generate_token():
    response = client.post("/token/generateToken")
    assert response.status_code == 200
    data = response.json()
    assert data == "token successfully generated"

@pytest.mark.asyncio
async def test_acquire_token():
    token_uuid = str(uuid.uuid4())
    token_key = f'token:{token_uuid}'  # Match the format used in your service logic
    generate_tokens_set.add(token_key)
    response = client.get("/token/acquireToken")
    generate_tokens_set.clear()
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert isinstance(data["token"], str)

@pytest.mark.asyncio
async def test_delete_token():
    # Generate a valid UUID to send in the request
    token_uuid = str(uuid.uuid4())
    token_key = f'token:{token_uuid}'  # Match the format used in your service logic
    generate_tokens_set.add(token_key)
    response = client.request("DELETE","/token/deleteToken", json={"token": token_uuid})
    assert response.status_code == 200
    data = response.json()
    print(data)
    assert data == f"{str(token_uuid)} has been deleted"

@pytest.mark.asyncio
async def test_keep_alive():
    # Generate a valid UUID to send in the request
    token = str(uuid.uuid4())
    token_key = f"token:{token}"
    generate_tokens_set.add(token_key)
    response = client.put("/token/keepAlive", json={"token": token})
    assert response.status_code == 200
    data = response.json()
    print(data)
    assert data == f"Token token=UUID('{token}') has received keep alive signal"

@pytest.mark.asyncio
async def test_unblock_token():
    # Generate a valid UUID to send in the request
    token_uuid = str(uuid.uuid4())
    token_key = f'token:{token_uuid}'  # Match the format used in your service logic
    assigned_tokens_set.add(token_key)
    generate_tokens_set.add(token_key)
    response = client.put("/token/unblockToken", json={"token": token_uuid})
    assert response.status_code == 200
    data = response.json()
    assert data == f"{token_uuid} has been unblocked"


@pytest.mark.asyncio
async def test_acquire_token_no_unassigned():
    # No tokens are available to acquire
    generate_tokens_set.clear()
    response = client.get("/token/acquireToken")
    assert response.status_code == 400
    data = response.json()
    assert data == {"detail":"No available tokens"}

@pytest.mark.asyncio
async def test_delete_token_not_exist():
    # Attempt to delete a non-existent token
    response = client.request("DELETE", "/token/deleteToken", json={"token": str(uuid.uuid4())})
    assert response.status_code == 400
    data = response.json()
    assert data == {"detail":"No such token in system"}

@pytest.mark.asyncio
async def test_keep_alive_token_not_exist():
    # Attempt to send keep-alive to a non-existent token
    response = client.put("/token/keepAlive", json={"token": str(uuid.uuid4())})
    assert response.status_code == 400
    data = response.json()
    assert data == {"detail":"No such token found"}

@pytest.mark.asyncio
async def test_unblock_token_not_assigned():
    # Attempt to unblock a token that is not assigned
    token_uuid = str(uuid.uuid4())
    token_key = f'token:{token_uuid}'
    generate_tokens_set.add(token_key)  # Add it to simulate existence but not assigned
    response = client.put("/token/unblockToken", json={"token": token_uuid})
    assert response.status_code == 400
    data = response.json()
    assert data == {"detail": "This token is not assigned and hence cannot be unblocked"}