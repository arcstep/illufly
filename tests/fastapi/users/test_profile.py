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
    assert user_info is not None, "用户信息不应为空"
    assert "password_hash" not in user_info, "敏感信息不应该包含在返回数据中"

def test_update_user_roles(users_manager, exist_user):
    """测试更新用户角色
    验证点:
    - 验证角色更新是否成功
    - 验证新角色是否正确保存
    """
    new_roles = [UserRole.USER, UserRole.OPERATOR]
    result = users_manager.update_user_roles(exist_user.user_id, new_roles)
    assert result.success, f"更新用户角色失败: {result.error}"
    
    user_info = users_manager.get_user_info(exist_user.user_id)
    assert user_info is not None, "用户信息不应为空"
    assert UserRole.OPERATOR.value in user_info["roles"], "新角色未被正确保存"

def test_change_user_password(users_manager, exist_user, test_user_password):
    """测试修改用户密码
    验证点:
    - 验证旧密码是否可以被验证成功
    - 验证密码修改是否成功
    - 验证新修改的密码是否可以被验证成功
    - 验证旧密码是否已经无效
    """
    # 验证旧密码
    old_verify_result = users_manager.verify_user_password(exist_user.username, test_user_password)
    assert old_verify_result.success, f"旧密码验证失败: {old_verify_result.error}"

    # 修改密码
    new_password = "NewPass123!"
    change_result = users_manager.change_password(exist_user.user_id, test_user_password, new_password)
    assert change_result.success, f"密码修改失败: {change_result.error}"

    # 验证新密码
    new_verify_result = users_manager.verify_user_password(exist_user.username, new_password)
    assert new_verify_result.success, f"新密码验证失败: {new_verify_result.error}"

    # 确认旧密码已失效
    old_verify_result = users_manager.verify_user_password(exist_user.username, test_user_password)
    assert not old_verify_result.success, "旧密码应该已经失效"

def test_nonexistent_user_operations(users_manager):
    """测试对不存在用户的操作
    验证点:
    - 验证各种操作对不存在用户的处理
    """
    # 获取用户信息
    user_info = users_manager.get_user_info("nonexistent")
    assert user_info is None, "不存在的用户应该返回None"
    
    # 更新用户信息
    update_result = users_manager.update_user("nonexistent", username="new_name")
    assert not update_result.success, "更新不存在的用户应该返回失败"
    
    # 删除用户
    delete_result = users_manager.delete_user("nonexistent")
    assert not delete_result.success, "删除不存在的用户应该返回失败"

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
    assert not result.success, "包含@的用户名应该被拒绝"
    assert "用户名只能包含" in result.error, f"错误信息不正确: {result.error}"

    # 测试有效的用户名和特殊邮箱
    valid_data = {
        "username": "test_user_123",  # 只包含字母、数字和下划线
        "email": "test+special@example.com",
        "password": "TestPass123!"
    }
    result = users_manager.create_user(**valid_data)
    assert result.success, f"创建有效用户失败: {result.error}"

    # 测试以数字开头的无效用户名
    invalid_start_data = {
        "username": "123test",
        "email": "test@example.com",
        "password": "TestPass123!"
    }
    result = users_manager.create_user(**invalid_start_data)
    assert not result.success, "以数字开头的用户名应该被拒绝"
    assert "用户名必须以字母开头" in result.error, f"错误信息不正确: {result.error}"
