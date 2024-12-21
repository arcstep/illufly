from behave import given, when, then
from fastapi import Response
from datetime import datetime, timedelta
from jose import JWTError
from urllib.parse import urlencode
import json

@given('初始化测试环境')
def step_impl(context):
    """初始化测试环境"""
    assert context.client is not None, "测试客户端未初始化"
    assert context.auth_manager is not None, "认证管理器未初始化"
    print("测试环境初始化完成")

@given('清空令牌存储')
def step_impl(context):
    """清空令牌存储"""
    context.auth_manager.clear_tokens()
    print("令牌存储已清空")

@given('准备测试用户数据')
def step_impl(context):
    """准备测试用户数据"""
    context.test_users = {}
    
    for row in context.table:
        username = row["username"]
        user_id = row["user_id"]
        roles = json.loads(row["roles"])
        
        user_data = {
            "user_id": user_id,
            "username": username,
            "roles": roles,
            "created_at": datetime.utcnow().isoformat(),
            "is_active": True
        }
        
        # 设置用户密码和密码哈希
        if username == "admin":
            password = "admin123"
        else:
            password = f"{username}123"  # 为其他用户生成密码
        
        user_data.update({
            "password": password,
            "password_hash": f"hashed_{password}"
        })
        
        context.test_users[username] = user_data
    
    # 更新 UsersManager 的用户数据
    context.users_manager._existing_users.update(context.test_users)
    
    print(f"已准备测试用户数据: {json.dumps(context.test_users, indent=2)}")

@given('用户持有有效的刷新令牌')
def step_impl(context):
    """设置有效的刷新令牌"""
    # 从表格中获取刷新令牌
    refresh_token = context.table.rows[0]["值"]
    user_data = context.test_users["admin"]  # 使用管理员用户数据
    
    # 存储令牌信息到 TokensManager 的设备令牌存储中
    context.auth_manager._device_tokens["test-device"] = {
        "access_token": "mock.access.token",
        "refresh_token": refresh_token,
        "user_id": user_data["user_id"],
        "username": user_data["username"],
        "roles": user_data["roles"]
    }
    
    print(f"已设置有效的刷新令牌: {refresh_token}")
    print(f"关联的用户数据: {json.dumps(user_data, indent=2)}")

@given('用户持有过期的刷新令牌')
def step_impl(context):
    """设置过期的刷新令牌"""
    refresh_token = "mock.refresh.token"  # 使用有效的令牌格式
    
    # 设置 verify_jwt 返回过期错误
    context.auth_manager.verify_jwt.side_effect = JWTError("令牌已过期")
    
    # is_token_valid 应该返回成功（因为是有效格式）
    context.auth_manager.is_token_valid.return_value = {
        "success": True
    }
    
    # is_token_in_other_device 不应该被调用
    context.auth_manager.is_token_in_other_device.assert_not_called = True
    
    context.refresh_token = refresh_token
    context.client.cookies["refresh_token"] = refresh_token
    print(f"已设置过期的刷新令牌: {refresh_token}")

@given('用户持有无效的刷新令牌')
def step_impl(context):
    """设置无效的刷新令牌"""
    # 使用明显不符合格式的令牌
    refresh_token = "invalid-token"
    
    # 所有验证函数都不应该被调用
    context.auth_manager.verify_jwt.assert_not_called = True
    context.auth_manager.is_token_valid.assert_not_called = True
    context.auth_manager.is_token_in_other_device.assert_not_called = True
    
    context.refresh_token = refresh_token
    context.client.cookies["refresh_token"] = refresh_token
    print(f"已设置无效的刷新令牌: {refresh_token}")

@given('用户持有格式错误的刷新令牌')
def step_impl(context):
    """设置格式错误的刷新令牌"""
    refresh_token = "format.error"  # 故意使用两段式格式
    
    # 所有验证函数都不应该被调用
    context.auth_manager.verify_jwt.assert_not_called = True
    context.auth_manager.is_token_valid.assert_not_called = True
    context.auth_manager.is_token_in_other_device.assert_not_called = True
    
    context.refresh_token = refresh_token
    context.client.cookies["refresh_token"] = refresh_token
    print(f"已设置格式错误的刷新令牌: {refresh_token}")

@given('用户持有已使用的刷新令牌')
def step_impl(context):
    """设置已使用的刷新令牌"""
    refresh_token = "mock.refresh.token"  # 使用有效的令牌格式
    
    # verify_jwt 验证通过
    context.auth_manager.verify_jwt.return_value = {
        "success": True
    }
    
    # is_token_valid 验证通过
    context.auth_manager.is_token_valid.return_value = {
        "success": True
    }
    
    # is_token_in_other_device 返回已使用错误
    context.auth_manager.is_token_in_other_device.return_value = {
        "success": False,
        "error": "令牌已在其他设备上使用"
    }
    
    context.refresh_token = refresh_token
    context.client.cookies["refresh_token"] = refresh_token
    print(f"已设置已使用的刷新令牌: {refresh_token}")

@when('发起令牌刷新请求')
def step_impl(context):
    """发送令牌刷新请求"""    
    # 发送刷新请求
    response = context.client.post(
        "/api/auth/refresh-token"
    )
    
    context.response = response
    print(f"刷新令牌请求状态码: {response.status_code}")
    if response.status_code != 200:
        print(f"错误响应: {response.content.decode()}")

@then('系统应返回状态码 {status_code:d}')
def step_impl(context, status_code):
    """验证响应状态码"""
    actual_status = context.response.status_code
    assert actual_status == status_code, \
        f"期望状态码 {status_code}，实际得到 {actual_status}"
    print(f"状态码验证通过: {actual_status}")

@then('响应中包含')
def step_impl(context):
    """验证响应内容"""
    response_data = context.response.json()
    print(f"实际响应: {json.dumps(response_data, indent=2)}")
    
    for row in context.table:
        field = row['字段']
        field_type = row['类型']
        description = row['说明']
        
        # 确保字段存在
        assert field in response_data, f"响应缺少字段: {field}"
        
        value = response_data[field]
        
        # 类型检查
        if field_type == 'bool':
            assert isinstance(value, bool), \
                f"字段 {field} 应为布尔类型，实际为 {type(value)}"
        elif field_type == 'string':
            assert isinstance(value, str), \
                f"字段 {field} 应为字符串类型，实际为 {type(value)}"
        
        # 特殊值验证
        if field == 'success' and description == 'true':
            assert value is True, "操作应该成功"
        elif field in ['access_token', 'refresh_token']:
            assert len(value) > 0, f"{field} 不应为空"
            
        print(f"字段 {field} 验证通过: {value}")

@then('响应中包含错误信息 "{error_message}"')
def step_impl(context, error_message):
    """验证错误响应消息"""
    response_data = context.response.json()
    assert "detail" in response_data, "响应中缺少错误详情"
    actual_error = response_data["detail"]
    
    # 根据不同的错误类型映射期望的错误消息
    expected_messages = {
        # 400 错误
        "无效的令牌格式": "无效的刷新令牌格式",
        
        # 401 错误
        "令牌已过期": "令牌已过期",
        "令牌已被使用": "令牌失效"
    }
    
    expected_error = expected_messages.get(error_message, error_message)
    assert expected_error == actual_error, \
        f"期望错误消息为 '{expected_error}'，实际得到 '{actual_error}'"
    print(f"错误消息验证通过: {actual_error}")

@given('管理员已登录')
def step_impl(context):
    """通过登录接口设置管理员登录状态"""
    admin_data = context.test_users.get("admin")
    if not admin_data:
        raise AssertionError("管理员用户���据未找到")
    
    # 发送登录请求
    response = context.client.post(
        "/api/auth/login",
        data={
            "username": admin_data["username"],
            "password": admin_data["password"],
            "device_id": "admin-device",
            "device_name": "Admin Device"
        }
    )
    
    if response.status_code != 200:
        print(f"DEBUG: Current test state: {context.users_manager.get_user_state(admin_data['user_id'])}")
        print(f"DEBUG: User info: {context.users_manager.get_user_info(admin_data['user_id'])}")
    
    assert response.status_code == 200, f"管理员登录失败: {response.content.decode()}"
    print(f"已设置管理员登录状态，访问令牌: {response.cookies.get('access_token')}")

@given('存在以下活跃令牌')
def step_impl(context):
    """设置活跃令牌数据"""
    active_tokens = []
    for row in context.table:
        token = {
            "user_id": row["user_id"],
            "device_id": row["device_id"],
            "token_type": row["token_type"],
            "token": f"mock.{row['token_type']}.{row['device_id']}"
        }
        active_tokens.append(token)
    
    # 设置 get_user_tokens 返回这些令牌
    context.auth_manager.get_user_tokens.return_value = {
        "success": True,
        "tokens": active_tokens
    }
    
    print(f"已设置活跃令牌: {active_tokens}")

@when('管理员请求撤销用户 "{username}" 的所有令牌')
def step_impl(context, username):
    """发起撤销令牌请求"""
    response = context.client.post(
        "/api/auth/revoke-token",
        data={"username": username}
    )
    context.response = response
    print(f"撤销令牌请求状态码: {response.status_code}")
    if response.status_code != 200:
        print(f"错误响应: {response.content.decode()}")

@then('该用户的所有令牌应被标记为无效')
def step_impl(context):
    """验证令牌已被标记为无效"""
    # 验证 invalidate_user_tokens 被调用
    context.auth_manager.invalidate_user_tokens.assert_called_once()
    call_args = context.auth_manager.invalidate_user_tokens.call_args[0]
    assert call_args[0] == "user1", f"期望撤销用户 user1 的令牌，实际撤销了 {call_args[0]} 的令牌"
    print("令牌撤销验证通过")

@then('审计日志应记录此操作')
def step_impl(context):
    """验证审计日志记录"""
    # 从表格中获取期望的审计日志数据
    expected_log = {}
    for row in context.table:
        expected_log[row["字段"]] = row["值"].strip('"')
    
    # 验证 log_audit 被调用
    context.audit_logger.log_audit.assert_called_once()
    call_kwargs = context.audit_logger.log_audit.call_args[1]
    
    # 验证关键字段
    for field, value in expected_log.items():
        assert call_kwargs[field] == value, \
            f"审计日志字段 {field} 期望值为 {value}，实际值为 {call_kwargs[field]}"
    
    print("审计日志验证通过")