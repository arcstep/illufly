import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI, Request, Response
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from fastapi import HTTPException, status

from illufly.api.auth.tokens import TokensManager, TokenClaims, TokenType
from illufly.api.auth.users import UsersManager
from illufly.api.auth.api_keys import ApiKey, ApiKeysManager

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
mock_api_keys_manager = MagicMock()

@pytest.fixture
def app():
    """创建测试应用"""
    app = FastAPI()
    return app

@pytest.fixture
def client(app):
    """创建测试客户端"""
    # 模拟管理器
    global mock_tokens_manager, mock_users_manager
    mock_tokens_manager = MagicMock()
    mock_users_manager = MagicMock()

    # 获取路由处理函数
    route_handlers = create_auth_endpoints(
        app=app,
        tokens_manager=mock_tokens_manager,
        users_manager=mock_users_manager,
        api_keys_manager=mock_api_keys_manager,
        prefix="/api"
    )

    # 注册路由
    for _, (method, path, handler) in route_handlers.items():
        getattr(app, method)(path)(handler)

    return TestClient(app)

@pytest.fixture
def mock_user_dict():
    """模拟用户信息"""
    return {
        "user_id": "123",
        "username": "testuser",
        "email": "testuser@example.com",
        "roles": ["user"]
    }

@pytest.fixture
def mock_token_dict(mock_user_dict):
    """模拟令牌信息"""
    return {
        "token_type": TokenType.ACCESS,
        "user_id": "123",
        "username": "testuser",
        "roles": ["user"],
        "device_id": "device123"
    }

class TestUsersManager:

    @pytest.mark.asyncio
    async def test_register_success(self, client):
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
    async def test_login_success(self, client, mock_user_dict, mock_token_dict):
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
            data=mock_token_dict,
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
    async def test_logout_success(self, client, mock_token_dict):
        # 1. 模拟令牌验证
        mock_tokens_manager.verify_access_token.return_value = Result.ok(
            data=mock_token_dict,
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
    async def test_change_password_success(self, client, mock_token_dict):
        mock_tokens_manager.verify_access_token.return_value = Result.ok(
            data=mock_token_dict,
            message="验证访问令牌成功"
        )
        mock_users_manager.change_password.return_value = Result.ok(
            message="密码修改成功"
        )

        # 测试数据
        payload = {
            "current_password": "oldpassword",
            "new_password": "newpassword"
        }

        client.cookies.set("access_token", "valid_token")
        response = client.post("/api/auth/change-password", json=payload)
        logger.info(f"修改密码结果: {response.json()}, cookies: {response.cookies}")

        # 验证结果
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_change_password_failure(self, client, mock_token_dict):
        mock_tokens_manager.verify_access_token.return_value = Result.ok(
            data=mock_token_dict,
            message="验证访问令牌成功"
        )
        mock_users_manager.change_password.return_value = Result.fail(
            error="当前密码错误"
        )

        # 测试数据
        payload = {
            "current_password": "wrongpassword",
            "new_password": "newpassword"
        }

        client.cookies.set("access_token", "valid_token")
        response = client.post("/api/auth/change-password", json=payload)

        # 验证结果
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "当前密码错误" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_user_profile_success(self, client, mock_token_dict):
        mock_tokens_manager.verify_access_token.return_value = Result.ok(
            data=mock_token_dict,
            message="验证访问令牌成功"
        )

        # 调用获取用户信息接口
        client.cookies.set("access_token", "valid_token")
        response = client.get("/api/auth/profile")

        # 验证结果
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["username"] == "testuser"

    @pytest.mark.asyncio
    async def test_update_user_profile_success(self, client, mock_user_dict, mock_token_dict):
        mock_tokens_manager.verify_access_token.return_value = Result.ok(
            data=mock_token_dict,
            message="验证访问令牌成功"
        )

        mock_users_manager.update_user.return_value = Result.ok(
            message="用户信息更新成功",
            data={**mock_user_dict, "username": "new_username"}
        )
        mock_tokens_manager.refresh_access_token.return_value = Result.ok(
            data={**mock_token_dict, "username": "new_username"},
        )
        # 测试数据
        payload = {
            "to_update": {
                "username": "new_username"
            }
        }

        client.cookies.set("access_token", "valid_token")
        response = client.post("/api/auth/profile", json=payload)
        logger.info(f"更新用户信息结果: {response.json()}, cookies: {response.cookies}")

        # 验证结果
        assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_require_user_success(self, mock_token_dict):
        # 这个测试用例需要单独处理，因为它测试中间件
        mock_tokens_manager.verify_access_token.return_value = Result.ok(
            data=mock_token_dict,
            message="验证访问令牌成功"
        )

        # 创建请求和响应对象
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/auth/profile",
            "headers": [(b"cookie", b"access_token=valid_token")]
        }
        request = Request(scope=scope)
        response = Response()

        # 调用中间件
        middleware = require_user(mock_tokens_manager)
        result = await middleware(request, response)

        # 验证结果
        assert result["roles"] == ["user"]

class TestApiKeyEndpoints:
    def test_create_api_key_success(self, client, mock_token_dict):
        """测试成功创建 API 密钥"""
        # 准备测试数据
        test_api_key = {
            "user_id": "test_user",
            "description": "Test Key"
        }

        mock_api_keys_manager.create_api_key.return_value = Result.ok(data=test_api_key)

        # 调用获取用户信息接口
        mock_tokens_manager.verify_access_token.return_value = Result.ok(data=mock_token_dict)
        client.cookies.set("access_token", "valid_token")
        # 发送请求
        payload = test_api_key
        response = client.post(
            "/api/auth/api-keys",
            json=payload,
            headers={"Cookie": "access_token=valid_token"}
        )
        logger.info(f"创建 API 密钥结果: {response.json()}, cookies: {response.cookies}")

        # 验证结果
        assert response.status_code == 200

    def test_list_api_keys_success(self, client, mock_token_dict):
        """测试成功列出 API 密钥"""
        # 准备测试数据
        test_keys = [
            {
                "user_id": "test_user",
                "description": "Key 1"
            },
            {
                "user_id": "test_user",
                "description": "Key 2"
            }
        ]
        mock_api_keys_manager.list_api_keys.return_value = Result.ok(data=test_keys)

        # 发送请求
        mock_tokens_manager.verify_access_token.return_value = Result.ok(data=mock_token_dict)
        client.cookies.set("access_token", "valid_token")
        response = client.get(
            "/api/auth/api-keys",
            headers={"Cookie": "access_token=valid_token"}
        )

        # 验证结果
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) == 2
        assert all(key["user_id"] == "test_user" for key in data["data"])

    def test_delete_api_key_success(self, client, mock_token_dict):
        """测试成功删除 API 密钥"""
        # 准备测试数据
        mock_api_keys_manager.delete_api_key.return_value = Result.ok()

        # 发送请求
        mock_tokens_manager.verify_access_token.return_value = Result.ok(data=mock_token_dict)
        client.cookies.set("access_token", "valid_token")
        response = client.delete(
            "/api/auth/api-keys/sk_test123",
            headers={"Cookie": "access_token=valid_token"}
        )

        # 验证结果
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_create_api_key_unauthorized(self, client, mock_token_dict):
        """测试未授权创建 API 密钥"""
        mock_tokens_manager.verify_access_token.return_value = Result.fail(
            error="未授权"
        )
        payload = {
            "user_id": "test_user",
            "description": "Test Key"
        }
        response = client.post(
            "/api/auth/api-keys",
            json=payload,
            headers={"Cookie": "access_token=valid_token"}
        )
        assert response.status_code == 401

    def test_list_api_keys_error(self, client, mock_token_dict):
        """测试列出 API 密钥时发生错误"""
        mock_tokens_manager.verify_access_token.return_value = Result.ok(data=mock_token_dict)
        client.cookies.set("access_token", "valid_token")
        mock_api_keys_manager.list_api_keys.return_value = Result.fail(
            error="数据库错误"
        )

        response = client.get(
            "/api/auth/api-keys",
            headers={"Cookie": "access_token=valid_token"}
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "数据库错误"

    def test_delete_api_key_not_found(self, client, mock_token_dict):
        """测试删除不存在的 API 密钥"""
        mock_tokens_manager.verify_access_token.return_value = Result.ok(data=mock_token_dict)
        client.cookies.set("access_token", "valid_token")
        mock_api_keys_manager.delete_api_key.return_value = Result.fail(
            error="API密钥不存在"
        )

        response = client.delete(
            "/api/auth/api-keys/sk_nonexistent",
            headers={"Cookie": "access_token=valid_token"}
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "API密钥不存在"