import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI, Request, Response
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from fastapi import HTTPException, status

from illufly.api.auth.tokens import TokensManager, TokenClaims, TokenType
from illufly.api.api_keys import create_api_keys_endpoints

from illufly.api.auth.endpoints import (
    Result,
)

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 模拟数据库

mock_tokens_manager = MagicMock()
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
    global mock_tokens_manager
    mock_tokens_manager = MagicMock()

    # 获取路由处理函数
    route_handlers = create_api_keys_endpoints(
        app=app,
        tokens_manager=mock_tokens_manager,
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