import pytest
from illufly.fastapi.users import UsersManager

class TestValidation:
    """验证相关测试"""

    @pytest.mark.parametrize("password,is_valid", [
        ("Short1", False),  # 太短
        ("nouppercase1", False),  # 没有大写字母
        ("NOLOWERCASE1", False),  # 没有小写字母
        ("NoNumbers", False),  # 没有数字
        ("ValidPass123", True),  # 有效密码
    ])
    def test_password_validation(self, users_manager, password, is_valid):
        """测试密码验证
        验证点:
        - 验证密码长度
        - 验证密码包含大写字母
        - 验证密码包含小写字母
        - 验证密码包含数字
        """
        result = users_manager.validate_password(password)
        assert result["success"] is is_valid

    @pytest.mark.parametrize("email,is_valid", [
        ("invalid", False),
        ("no@domain", False),
        ("valid@example.com", True),
        ("user.name+tag@example.co.uk", True),
    ])
    def test_email_validation(self, users_manager, email, is_valid):
        """测试邮箱验证
        验证点:
        - 验证邮箱格式是否正确
        """
        result = users_manager.validate_email(email)
        assert result["success"] is is_valid

    @pytest.mark.parametrize("username,is_valid", [
        ("ab", False),  # 太短
        ("123user", False),  # 不能以数字开头
        ("valid_user123", True),
        ("very_long_username_that_exceeds_32_chars", False),
    ])
    def test_username_validation(self, users_manager, username, is_valid):
        """测试用户验证
        验证点:
        - 验证用户名长度
        - 验证用户名不能以数字开头
        - 验证用户名的最大长度
        """
        result = users_manager.validate_username(username)
        assert result["success"] is is_valid 
