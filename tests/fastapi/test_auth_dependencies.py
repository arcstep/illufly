import pytest
from fastapi import FastAPI, Request, Response, HTTPException
from unittest.mock import Mock, patch
from illufly.fastapi.auth.dependencies import AuthDependencies
from illufly.fastapi.user import UserRole, User

pytestmark = pytest.mark.anyio

@pytest.fixture
def auth_manager():
    return Mock()

@pytest.fixture
def auth_dependencies(auth_manager):
    return AuthDependencies(auth_manager)

class TestGetCurrentUser:
    async def test_valid_access_token(self, auth_dependencies):
        """测试有效的访问令牌"""
        mock_request = Mock()
        mock_request.cookies = {"access_token": "valid_token"}
        mock_response = Mock()
        
        auth_dependencies.auth_manager.is_token_valid.return_value = {"success": True}
        auth_dependencies.auth_manager.verify_jwt.return_value = {
            "success": True,
            "payload": {"user_id": "123"}
        }
        
        result = await auth_dependencies.get_current_user(mock_request, mock_response)
        assert result == {"user_id": "123"}

    async def test_invalid_access_token_valid_refresh(self, auth_dependencies):
        mock_request = Mock()
        mock_request.cookies = {
            "access_token": "invalid_token",
            "refresh_token": "valid_refresh"
        }
        
        auth_dependencies.auth_manager.is_token_valid.side_effect = [
            {"success": False},  # access token
            {"success": True}    # refresh token
        ]
        
        auth_dependencies.auth_manager.verify_jwt.return_value = {
            "success": True,
            "payload": {"user_id": "123"}
        }
        
        auth_dependencies.auth_manager.create_access_token.return_value = {
            "success": True,
            "token": "new_token"
        }
        
        mock_response = Mock()
        
        result = await auth_dependencies.get_current_user(mock_request, mock_response)
        assert result == {"user_id": "123"}

    async def test_all_tokens_invalid(self, auth_dependencies):
        mock_request = Mock()
        mock_request.cookies = {
            "access_token": "invalid_token",
            "refresh_token": "invalid_refresh"
        }
        
        auth_dependencies.auth_manager.is_token_valid.return_value = {"success": False}
        
        mock_response = Mock()
        
        with pytest.raises(HTTPException) as exc:
            await auth_dependencies.get_current_user(mock_request, mock_response)
        assert exc.value.status_code == 401

class TestRequireRoles:
    async def test_has_required_role(self, auth_dependencies):
        """测试用户具有所需角色"""
        # 创建 mock 对象
        mock_request = Mock(spec=Request)
        mock_response = Mock(spec=Response)
        
        mock_user_data = {
            "user_id": "123",
            "username": "test_user",
            "roles": ["admin"],
            "created_at": "2024-01-01T00:00:00"
        }
        role_checker = auth_dependencies.require_roles(UserRole.ADMIN)
        
        async def mock_get_current_user(*args, **kwargs):
            return mock_user_data
            
        with patch.object(auth_dependencies, 'get_current_user', 
                         side_effect=mock_get_current_user):
            result = await role_checker(mock_request, mock_response)
            assert result == mock_user_data

    async def test_missing_required_role(self, auth_dependencies):
        """测试用户缺少所需角色"""
        # 创建 mock 对象
        mock_request = Mock(spec=Request)
        mock_response = Mock(spec=Response)
        
        mock_user_data = {
            "user_id": "123",
            "username": "test_user",
            "roles": ["user"],
            "created_at": "2024-01-01T00:00:00"
        }
        role_checker = auth_dependencies.require_roles(UserRole.ADMIN)
        
        async def mock_get_current_user(*args, **kwargs):
            return mock_user_data
            
        with patch.object(auth_dependencies, 'get_current_user', 
                         side_effect=mock_get_current_user):
            with pytest.raises(HTTPException) as exc:
                await role_checker(mock_request, mock_response)
            assert exc.value.status_code == 403
