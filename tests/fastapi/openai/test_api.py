import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_chat_completion():
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "Hello!"}]
        },
        headers={"Authorization": "Bearer sk-1234567890abcdef"}
    )
    assert response.status_code == 200
    assert response.json()["object"] == "chat.completion"
    assert len(response.json()["choices"]) > 0

def test_invalid_api_key():
    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "Hello!"}]
        },
        headers={"Authorization": "Bearer invalid-key"}
    )
    assert response.status_code == 401
