import pytest
from illufly.fastapi.users import User, UserRole

class TestAuthentication:
    """认证相关测试"""

    @pytest.fixture()
    def exist_user(self, users_manager, test_user, test_user_password):
        """已存在的用户"""
        users_manager.create_user(
            email=test_user.email,
            username=test_user.username,
            password=test_user_password
        )
        return test_user

    def test_register_user(self, users_manager, test_user, test_user_password):
        """测试注册用户"""
        result = users_manager.create_user(
            email=test_user.email,
            username=test_user.username,
            password=test_user_password
        )
        assert result["success"] is True, f"Register user failed: {result.get('error')}"
    
    def test_login_success(self, users_manager, exist_user, test_user_password):
        """测试登录成功"""
        result = users_manager.verify_user_password(exist_user.username, test_user_password)
        assert result["success"] is True, f"Login failed: {result.get('error')}"

    def test_login_wrong_password(self, users_manager, exist_user):
        """测试密码错误"""
        result = users_manager.verify_user_password(exist_user.username, "wrong_password")
        assert result["success"] is False, f"Login should fail with wrong password"
