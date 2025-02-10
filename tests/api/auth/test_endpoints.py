import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from fastapi import HTTPException, status

from illufly.api.auth.tokens import TokensManager, TokenClaims, TokenType
from illufly.api.auth.users import UsersManager
from illufly.api.auth.endpoints import (
    create_auth_endpoints,
    require_user,
    Result,
    User
)

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 模拟数据库

mock_tokens_manager = MagicMock()
mock_users_manager = MagicMock()

# 生成测试客户端
@pytest.fixture
def client():
    app = FastAPI()
    endpoints = create_auth_endpoints(app, mock_tokens_manager, mock_users_manager, prefix="/api")
    client = TestClient(app)
    return client

@pytest.mark.asyncio
async def test_register_success(client):
    # 模拟 UsersManager
    mock_users_manager.create_user.return_value = Result.ok(
        data=User(
            user_id="test_id",
            username="testuser",
            email="testuser@example.com",
            roles=["user"]
        ).model_dump(exclude={"password_hash"}),
        message="用户创建成功"
    )
    
    # 测试数据
    payload = {
        "username": "testuser",
        "password": "password123",
        "email": "testuser@example.com"
    }

    # 调用注册接口
    response = client.post("/api/auth/register", json=payload)
    logger.info(f"注册结果: {response.json()}")

    # 验证结果
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert response_data["message"] == "用户创建成功"
    assert "data" in response_data
    assert response_data["data"]["username"] == "testuser"
    assert response_data["data"]["email"] == "testuser@example.com"
    assert "password_hash" not in response_data["data"]

@pytest.mark.asyncio
async def test_login_success(client):
    # 模拟验证密码成功
    mock_users_manager.verify_password.return_value = Result.ok(
        data=User(
            is_locked=False,
            is_active=True,
            user_id="123",
            roles=["user"],
            username="testuser"
        ).model_dump(exclude={"password_hash"}),
        message="登录成功"
    )
    mock_tokens_manager.refresh_access_token.return_value = Result.ok(
        data={
            "token_type": TokenType.ACCESS,
            "user_id": "123",
            "username": "testuser",
            "roles": ["user"],
            "device_id": "device123"
        },
        message="访问令牌刷新成功"
    )

    # 测试数据
    payload = {
        "username": "testuser",
        "password": "password123"
    }

    # 调用登录接口
    response = client.post("/api/auth/login", json=payload)
    logger.info(f"登录结果: {response.json()}, cookies: {response.cookies}")

    # 验证结果
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["message"] == "登录成功"
    assert "access_token" in response.cookies

@pytest.mark.asyncio
async def test_logout_success(client):
    # 1. 模拟令牌验证
    mock_tokens_manager.verify_access_token.return_value = Result.ok(
        data={
            "user_id": "123",
            "device_id": "device123",
            "username": "testuser",
            "roles": ["user"]
        },
        message="验证访问令牌成功"
    )

    # 2. 模拟令牌撤销
    mock_tokens_manager.revoke_refresh_token.return_value = Result.ok(
        message="刷新令牌撤销成功"
    )
    mock_tokens_manager.revoke_access_token.return_value = Result.ok(
        message="访问令牌撤销成功"
    )

    # 3. 调用注销接口
    client.cookies.set("access_token", "valid_token")
    response = client.post("/api/auth/logout")
    logger.info(f"注销结果: {response.json()}, cookies: {response.cookies}")

    # 4. 验证结果
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert response_data["message"] == "注销成功"
    
    # 5. 验证方法调用
    mock_tokens_manager.revoke_refresh_token.assert_called_once_with(
        user_id="123",
        device_id="device123"
    )
    mock_tokens_manager.revoke_access_token.assert_called_once_with(
        user_id="123",
        device_id="device123"
    )

    # 6. 验证 cookie 删除
    assert "access_token" not in response.cookies

@pytest.mark.asyncio
async def test_change_password_success(client):
    mock_users_manager.change_password.return_value = Result.ok(
        message="密码修改成功"
    )

    # 测试数据
    payload = {
        "current_password": "oldpassword",
        "new_password": "newpassword"
    }

    response = client.post("/api/auth/change-password", json=payload)

    # 验证结果
    assert response.status_code == status.HTTP_200_OK

@pytest.mark.asyncio
async def test_change_password_failure(client):
    mock_users_manager.change_password.return_value = Result.fail(
        error="当前密码错误"
    )

    # 测试数据
    payload = {
        "current_password": "wrongpassword",
        "new_password": "newpassword"
    }

    response = client.post("/api/auth/change-password", json=payload)

    # 验证结果
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "当前密码错误" in response.json()["detail"]

@pytest.mark.asyncio
async def test_get_user_profile_success(client):
    mock_tokens_manager.verify_access_token.return_value = Result.ok(
        data={
            "user_id": "123",
            "username": "testuser",
            "roles": ["user"]
        }
    )

    # 调用获取用户信息接口
    response = client.get("/api/auth/profile", cookies={"access_token": "valid_token"})

    # 验证结果
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["data"]["username"] == "testuser"

@pytest.mark.asyncio
async def test_require_user_success():
    mock_tokens_manager.verify_access_token.return_value = Result.ok(
        data={
            "roles": ["user"]
        }
    )

    # 调用鉴权中间件
    middleware = require_user(mock_tokens_manager, MagicMock())
    result = await middleware(MagicMock(), MagicMock())

    # 验证结果
    assert result.roles == ["user"]
