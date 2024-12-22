import pytest
from datetime import datetime, timedelta
from illufly.fastapi.users.users.models import User, UserRole

def test_get_user_info(users_manager, exist_user):
    """测试获取用户信息
    验证点:
    - 验证获取的用户信息是否完整
    - 验证敏感信息是否正确处理
    """
    user_info = users_manager.get_user_info(exist_user.user_id)
    assert user_info is not None
    assert "password_hash" not in user_info

def test_update_user_roles(users_manager, exist_user):
    """测试更新用户角色
    验证点:
    - 验证角色更新是否成功
    - 验证新角色是否正确保存
    """
    new_roles = [UserRole.USER, UserRole.OPERATOR]
    result = users_manager.update_user_roles(exist_user.user_id, new_roles)
    assert result["success"]
    
    updated_user = users_manager.get_user_info(exist_user.user_id)
    assert UserRole.OPERATOR.value in updated_user["roles"]

def test_chage_user_password(users_manager, exist_user, test_user_password):
    """测试修改用户密码
    验证点:
    - 验证旧密码是否可以被验证成功
    - 验证密码��改是否成功
    - 验证新修改的密码是否可以被验证成功
    - 验证旧密码是否已经无效
    """
    old_verified = users_manager.verify_user_password(exist_user.username, test_user_password)
    assert old_verified["success"]

    new_password = "NewPass123!"
    result = users_manager.change_password(exist_user.user_id, test_user_password, new_password)
    print(result)
    assert result["success"]

    verified = users_manager.verify_user_password(exist_user.username, new_password)
    assert verified["success"]

    old_verified = users_manager.verify_user_password(exist_user.username, test_user_password)
    assert not old_verified["success"]

def test_nonexistent_user_operations(users_manager):
    """测试对不存在用户的操作
    验证点:
    - 验证各种操作对不存在用户的处理
    """
    assert not users_manager.get_user_info("nonexistent")
    assert not users_manager.update_user("nonexistent", username="new_name")["success"]
    assert not users_manager.delete_user("nonexistent")["success"]

def test_special_characters_handling(users_manager):
    """测试特殊字符处理
    验证点:
    - 验证用户名中特殊字符的处理
    - 验证邮箱中特殊字符的处理
    """
    # 测试包含@的无效用户名
    invalid_username_data = {
        "username": "test_user@123",
        "email": "test@example.com",
        "password": "TestPass123!"
    }
    result = users_manager.create_user(**invalid_username_data)
    assert not result["success"]
    assert "用户名只能包含" in result["error"]

    # 测试有效的用户名和特殊邮箱
    valid_data = {
        "username": "test_user_123",  # 只包含字母、数字和下划线
        "email": "test+special@example.com",
        "password": "TestPass123!"
    }
    result = users_manager.create_user(**valid_data)
    assert result["success"]

    # 测试以数字开头的无效用户名
    invalid_start_data = {
        "username": "123test",
        "email": "test@example.com",
        "password": "TestPass123!"
    }
    result = users_manager.create_user(**invalid_start_data)
    assert not result["success"]
    assert "用户名必须以字母开头" in result["error"]
