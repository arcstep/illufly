import pytest
from datetime import datetime, timedelta
from pydantic import ValidationError

from illufly.api.auth.models import UserRole, User, PasswordHasher

# 测试 UserRole 的方法
class TestUserRole:
    def test_has_role(self):
        """测试 has_role 方法"""
        roles = {UserRole.ADMIN}
        assert UserRole.has_role(UserRole.ADMIN, roles) is True
        assert UserRole.has_role(UserRole.OPERATOR, roles) is True
        assert UserRole.has_role(UserRole.USER, roles) is True
        assert UserRole.has_role(UserRole.GUEST, roles) is True  # GUEST 是 ADMIN 的子角色

        roles = {UserRole.OPERATOR}
        assert UserRole.has_role(UserRole.ADMIN, roles) is False
        assert UserRole.has_role(UserRole.OPERATOR, roles) is True
        assert UserRole.has_role(UserRole.USER, roles) is True
        assert UserRole.has_role(UserRole.GUEST, roles) is True

        roles = {UserRole.USER}
        assert UserRole.has_role(UserRole.ADMIN, roles) is False
        assert UserRole.has_role(UserRole.OPERATOR, roles) is False
        assert UserRole.has_role(UserRole.USER, roles) is True
        assert UserRole.has_role(UserRole.GUEST, roles) is True

        roles = {UserRole.GUEST}
        assert UserRole.has_role(UserRole.ADMIN, roles) is False
        assert UserRole.has_role(UserRole.OPERATOR, roles) is False
        assert UserRole.has_role(UserRole.USER, roles) is False
        assert UserRole.has_role(UserRole.GUEST, roles) is True


# 测试 User 的方法
class TestUser:
    @pytest.fixture
    def sample_user(self):
        """创建一个示例用户"""
        return User(
            username="alice",
            password_hash="hashed_password",
            email="alice@example.com",
            mobile="1234567890",
            roles={UserRole.USER},
        )

    def test_can_update_field(self):
        """测试 can_update_field 方法"""
        assert User.can_update_field(["username", "email"]) is True
        assert User.can_update_field(["password_hash"]) is False

    def test_generate_random_password(self):
        """测试 generate_random_password 方法"""
        password = User.generate_random_password(length=12)
        assert len(password) == 12
        assert any(char.isdigit() for char in password)
        assert any(char in "!@#$%^&*" for char in password)

    def test_hash_password(self):
        """测试 hash_password 方法"""
        password = "secure_password"
        hashed_password = User.hash_password(password)
        assert isinstance(hashed_password, str)
        assert hashed_password != password

    def test_verify_password(self, sample_user):
        """测试 verify_password 方法"""
        password = "secure_password"
        hashed_password = sample_user.hash_password(password)
        sample_user.password_hash = hashed_password

        # 验证正确的密码
        result = sample_user.verify_password(password)
        assert result["rehash"] is False

        # 验证错误的密码
        with pytest.raises(Exception):  # Argon2 的 verify 方法会抛出异常
            sample_user.verify_password("wrong_password")

    def test_is_password_expired(self, sample_user):
        """测试 is_password_expired 方法"""
        # 设置最后修改时间为 100 天前
        sample_user.last_password_change = datetime.now() - timedelta(days=100)
        sample_user.password_expires_days = 90
        assert sample_user.is_password_expired() is True

        # 设置最后修改时间为 50 天前
        sample_user.last_password_change = datetime.now() - timedelta(days=50)
        assert sample_user.is_password_expired() is False

    def test_record_login_attempt_success(self, sample_user):
        """测试 record_login_attempt 成功登录"""
        sample_user.record_login_attempt(success=True)
        assert sample_user.failed_login_attempts == 0
        assert sample_user.is_locked is False
        assert sample_user.last_login is not None
        assert sample_user.last_failed_login is None

    def test_record_login_attempt_failure(self, sample_user):
        """测试 record_login_attempt 登录失败"""
        for _ in range(5):
            sample_user.record_login_attempt(success=False)

        assert sample_user.failed_login_attempts == 5
        assert sample_user.is_locked is True
        assert sample_user.last_failed_login is not None

    def test_validate_username(self):
        """测试 validate_username 方法"""
        # 合法用户名
        assert User(username="alice", password_hash="hashed").username == "alice"

        # 非法用户名
        with pytest.raises(ValidationError):
            User(username="1alice", password_hash="hashed")  # 不能以数字开头
        with pytest.raises(ValidationError):
            User(username="alice!", password_hash="hashed")  # 包含非法字符

    def test_validate_roles(self):
        """测试 validate_roles 方法"""
        user = User(username="alice", password_hash="hashed", roles=["user"])
        assert UserRole.USER in user.roles

        with pytest.raises(ValueError):
            User(username="alice", password_hash="hashed", roles=["invalid_role"])

    def test_verify_password_needs_rehash(self, sample_user):
        """测试 verify_password 触发重新哈希"""
        password = "secure_password"
        hashed_password = sample_user.hash_password(password)
        sample_user.password_hash = hashed_password

        # 修改哈希参数（例如增加 time_cost）
        ph = PasswordHasher(time_cost=4)  # 默认的 time_cost 可能是 3
        ph.verify(sample_user.password_hash, password)

        # 检查是否需要重新哈希
        if ph.check_needs_rehash(sample_user.password_hash):
            sample_user.password_hash = ph.hash(password)
            assert True  # 重新哈希成功
        else:
            assert False  # 未触发重新哈希