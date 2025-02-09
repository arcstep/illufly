import pytest

from argon2 import PasswordHasher
from unittest.mock import MagicMock
from datetime import datetime

from illufly.api.auth.users import UsersManager, UserRole, User
from illufly.rocksdb import IndexedRocksDB
from illufly.api.models import Result

# Mock 数据
USER_ID = "user_1"
USERNAME = "alice"
PASSWORD = "secure_password"
PASSWORD_HASH = PasswordHasher().hash(PASSWORD)
EMAIL = "alice@example.com"
MOBILE = "1234567890"
ROLES = [UserRole.USER]

ADMIN_USER_ID = "admin"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin"

@pytest.fixture
def mock_db():
    """模拟 IndexedRocksDB 实例"""
    db = MagicMock(spec=IndexedRocksDB)
    db.register_model = MagicMock(return_value=db)
    db.register_index = MagicMock(return_value=db)
    return db

@pytest.fixture
def users_manager(mock_db):
    """创建 UsersManager 实例"""
    manager = UsersManager(db=mock_db)
    return manager

def test_create_user(users_manager, mock_db):
    """测试创建新用户"""
    # 模拟数据库返回空值（用户名未被占用）
    mock_db.items_with_indexes.return_value = []

    # 创建用户
    user_data = {
        "user_id": USER_ID,
        "username": USERNAME,
        "password_hash": User.hash_password(PASSWORD),
        "email": EMAIL,
        "mobile": MOBILE,
        "roles": ROLES,
    }
    result = users_manager.create_user(User(**user_data))

    # 验证结果
    assert result.is_ok()
    created_user = result.data
    assert created_user.user_id == USER_ID
    assert created_user.username == USERNAME
    assert created_user.email == EMAIL
    assert created_user.mobile == MOBILE
    assert set(created_user.roles) == set(ROLES)

    # 验证数据库更新方法被调用
    mock_db.update_with_indexes.assert_called_once()

def test_get_user_info(users_manager, mock_db):
    """测试获取用户信息"""
    # 模拟数据库返回用户数据
    mock_db.__getitem__.return_value = {
        "user_id": USER_ID,
        "username": USERNAME,
        "email": EMAIL,
        "mobile": MOBILE,
        "roles": [role.value for role in ROLES],
        "password_hash": "hashed_password",
    }

    # 获取用户信息
    user_info = users_manager.get_user_info(USER_ID)

    # 验证结果
    assert user_info is not None
    assert user_info["user_id"] == USER_ID
    assert user_info["username"] == USERNAME
    assert user_info["email"] == EMAIL
    assert user_info["mobile"] == MOBILE
    assert "password_hash" not in user_info  # 敏感信息应被排除

def test_verify_password_success(users_manager, mock_db):
    """测试验证用户密码成功"""
    # 模拟数据库返回用户数据
    mock_db.values_with_indexes.return_value = [{
        "user_id": USER_ID,
        "username": USERNAME,
        "password_hash": PASSWORD_HASH,
    }]

    # 模拟密码验证成功
    users_manager._db.get.return_value.verify_password = MagicMock(return_value=True)

    # 验证密码
    result = users_manager.verify_password(USERNAME, PASSWORD)

    # 验证结果
    assert result.is_ok()
    assert result.data["user"]["user_id"] == USER_ID
    assert result.data["require_password_change"] is False

def test_verify_password_failure(users_manager, mock_db):
    """测试验证用户密码失败"""
    # 模拟数据库返回用户数据
    mock_db.values_with_indexes.return_value = [{
        "user_id": USER_ID,
        "username": USERNAME,
        "password_hash": PASSWORD_HASH,
    }]

    # 模拟密码验证失败
    users_manager._db.get.return_value.verify_password = MagicMock(return_value=False)

    # 验证密码
    result = users_manager.verify_password(USERNAME, "wrong_password")

    # 验证结果
    assert result.is_fail()
    assert "密码验证失败" in result.error

def test_change_password(users_manager, mock_db):
    """测试修改用户密码"""
    # 模拟数据库返回用户数据
    mock_db.__getitem__.return_value = {
        "user_id": USER_ID,
        "username": USERNAME,
        "password_hash": PASSWORD_HASH,
    }

    # 模拟旧密码验证成功
    users_manager._db.get.return_value.verify_password = MagicMock(return_value=True)

    # 修改密码
    result = users_manager.change_password(USER_ID, PASSWORD, "new_password")

    # 验证结果
    assert result.is_ok()

    # 验证数据库更新方法被调用
    mock_db.update_with_indexes.assert_called_once()

def test_reset_password(users_manager, mock_db):
    """测试重置用户密码"""
    # 模拟数据库返回用户数据
    mock_db.__getitem__.return_value = {
        "user_id": USER_ID,
        "username": USERNAME,
        "password_hash": PASSWORD_HASH,
    }

    # 重置密码
    result = users_manager.reset_password(USER_ID, "new_password")

    # 验证结果
    assert result.is_ok()

    # 验证数据库更新方法被调用
    mock_db.update_with_indexes.assert_called_once()

def test_ensure_admin_user_exists(users_manager, mock_db):
    """测试确保管理员用户存在"""
    # 确认管理员确认时返回空
    mock_db.get.return_value = None
    # 让唯一性检查时返回空
    mock_db.items_with_indexes.return_value = []

    # 确保管理员用户存在
    users_manager.ensure_admin_user()

    # 验证数据库更新方法被调用
    mock_db.update_with_indexes.assert_called_once()

    # 验证管理员用户的属性
    call_args = mock_db.update_with_indexes.call_args[0]
    admin_user = call_args[2]
    assert admin_user.user_id == ADMIN_USER_ID
    assert admin_user.username == ADMIN_USERNAME
    assert admin_user.roles == {UserRole.ADMIN}
    assert admin_user.require_password_change is False

def test_list_users(users_manager, mock_db):
    """测试列出所有用户"""
    # 模拟数据库返回多个用户
    mock_db.iter_model_keys.return_value = ["user_1", "user_2"]
    mock_db.__getitem__.side_effect = [
        {"user_id": "user_1", "username": "alice", "password_hash": PASSWORD_HASH},
        {"user_id": "user_2", "username": "bob", "password_hash": PASSWORD_HASH},
    ]

    # 列出用户
    users = users_manager.list_users()

    # 验证结果
    assert len(users) == 2
    assert users[0].user_id == "user_1"
    assert users[1].user_id == "user_2" 