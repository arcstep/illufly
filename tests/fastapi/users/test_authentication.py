import pytest
from illufly.fastapi.users import User, UserRole

class TestAuthentication:
    """认证相关测试
    测试用户注册和登录功能，包括成功和失败的场景。
    """

    def test_register_user(self, users_manager, test_user, test_user_password):
        """测试注册用户
        验证用户注册功能是否正常工作。
        """
        print(">>> users_manager: ", users_manager._storage._data_dir)
        result = users_manager.create_user(
            email=test_user.email,
            username=test_user.username,
            password=test_user_password
        )
        print(">>> register result: ", result)
        assert result.success, f"注册用户失败: {result.error}"
        assert result.data is not None, "注册成功但未返回用户数据"
        user, generated_password = result.data
        assert user.username == test_user.username
        assert user.email == test_user.email

    def test_register_duplicate_user(self, users_manager, exist_user, test_user_password):
        """测试创建重复用户
        验证点:
        - 验证创建重复用户名的结果
        - 验证创建重复邮箱的结果
        """
        result = users_manager.create_user(
            email=exist_user.email,
            username=exist_user.username,
            password=test_user_password
        )
        assert not result.success, "创建重复用户应该失败"
        assert result.error is not None, "应该返回错误信息"
        assert "已存在" in result.error, f"错误信息应该包含'已存在'，实际为: {result.error}"

    def test_login_success(self, users_manager, exist_user, test_user_password):
        """测试登录成功
        验证使用正确的用户名和密码登录是否成功。
        """
        result = users_manager.verify_user_password(exist_user.username, test_user_password)
        assert result.success, f"登录失败: {result.error}"
        assert result.data is not None, "登录成功但未返回用户数据"
        assert "user" in result.data, "返回数据中应包含用户信息"
        assert "require_password_change" in result.data, "返回数据中应包含密码更改要求"

    def test_login_wrong_password(self, users_manager, exist_user):
        """测试密码错误
        验证使用错误的密码登录是否失败。
        """
        result = users_manager.verify_user_password(exist_user.username, "wrong_password")
        assert not result.success, "使用错误密码登录应该失败"
        assert result.error is not None, "应该返回错误信息"
        assert "密码错误" in result.error.lower(), f"错误信息应该包含'密码错误'，实际为: {result.error}"

    def test_login_user_not_found(self, users_manager):
        """测试用户不存在
        验证使用不存在的用户名登录是否失败。
        """
        result = users_manager.verify_user_password("nonexistent_user", "any_password")
        assert not result.success, "使用不存在的用户名登录应该失败"
        assert result.error is not None, "应该返回错误信息"
        assert "不存在" in result.error.lower(), f"错误信息应该包含'不存在'，实际为: {result.error}"
