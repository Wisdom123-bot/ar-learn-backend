import pytest
from fastapi.testclient import TestClient
from main import app
from app.core.security import create_access_token, create_refresh_token, decode_token

client = TestClient(app)

def test_token_creation_and_decoding():
    data = {"sub": "test-user-id", "role": "teacher"}
    access_token = create_access_token(data)
    refresh_token = create_refresh_token(data)
    
    decoded_access = decode_token(access_token)
    decoded_refresh = decode_token(refresh_token)
    
    assert decoded_access["sub"] == "test-user-id"
    assert decoded_access["type"] == "access"
    
    assert decoded_refresh["sub"] == "test-user-id"
    assert decoded_refresh["type"] == "refresh"

def test_refresh_endpoint():
    # 1. Create a refresh token
    refresh_token = create_refresh_token({"sub": "test-id", "role": "teacher"})
    
    # 2. Call refresh endpoint
    response = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    
    assert response.status_code == 200
    assert "token" in response.json()
    
    # 3. Verify new access token
    new_access = response.json()["token"]
    decoded = decode_token(new_access)
    assert decoded["sub"] == "test-id"
    assert decoded["type"] == "access"

def test_invalid_refresh_token():
    response = client.post("/auth/refresh", json={"refresh_token": "invalid-token"})
    assert response.status_code == 401
