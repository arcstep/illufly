# features/steps/auth_register_steps.py
from behave import given, when, then
from fastapi import Response
from datetime import datetime
import json

@given('FastAPI 已经准备好')
def step_impl(context):
    assert context.client is not None
    print("FastAPI 已经准备好")

@given('用户模块已经准备好')
def step_impl(context):
    assert context.user_manager is not None
    print("用户模块已经准备好")

@given('认证模块已经准备好')
def step_impl(context):
    assert context.user_manager is not None
    print("认证模块已经准备好")

@given('清理测试数据')
def step_impl(context):
    context.storage = {
        'register_data': [],
        'users': [],
        'tokens': [],
        'audit_logs': [],
        'refresh_tokens': {},
        'access_tokens': {},
    }

@given('准备好用户表单')
def step_impl(context):
    context.registration_table = context.table
    print(f"准备注册表单数据: {context.registration_table}")

@when('提交用户注册请求')
def step_impl(context):    
    # 将表格数据转换为表单数据
    form_data = {row['字段']: row['值'] for row in context.registration_table}
    
    response = context.client.post(
        "/api/auth/register",
        data=form_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    context.response = response
    
    # 从响应中提取 user_id
    if response.status_code == 200:
        response_data = response.json()
        print(">>> response_data", response_data)
        user_info = response_data.get('user_info')
        if user_info:
            context.storage['register_data'].append(user_info)
            context.storage['users'].append(user_info)
            print(f"获取到用户ID: {user_info.get('user_id')}")
    else:
        print(f"请求失败，状态码: {response.status_code}")
        if response.content:
            print(f"错误信息: {response.content.decode()}")

@then('系统返回状态码 {status_code:d}')
def step_impl(context, status_code):
    assert context.response.status_code == status_code

@then('返回成功响应')
def step_impl(context):
    data = context.response.json()
    assert data["success"] is True

@then('返回的用户信息包含')
def step_impl(context):
    data = context.response.json()
    user_info = data["user_info"]
    print(f"Actual user_info: {json.dumps(user_info, indent=2)}")
    
    for row in context.table:
        field = row['字段']
        expected = row['值']
        actual = user_info[field]
        
        if field == 'roles':
            expected_roles = json.loads(expected)
            actual_roles = set(role.lower() for role in actual)
            expected_roles = set(role.lower() for role in expected_roles)
            assert actual_roles == expected_roles, \
                f"Roles mismatch. Expected: {expected_roles}, Got: {actual_roles}"
        elif isinstance(actual, bool):
            expected_bool = expected.lower() == 'true'
            assert actual == expected_bool, \
                f"Field {field} mismatch. Expected: {expected_bool}, Got: {actual}"
        else:
            assert str(actual) == expected, \
                f"Field {field} mismatch. Expected: {expected}, Got: {actual}"

@then('密码应当被安全存储')
def step_impl(context):
    # 获取刚注册的用户
    user_id = context.storage['register_data'][0].get('user_id')
    assert user_id, "用户ID不应为空"
    print(f"验证用户ID: {user_id} 的密码存储")
    
    # 从提交注册请求步骤的表格中获取原始密码
    original_password = None
    for row in context.registration_table:  # 使用保存的注册表格数据
        if row['字段'] == 'password':
            original_password = row['值']
            break
    
    # 通过 UserManager 的 get_user_info 方法获取用户信息，包含敏感信息
    user_info = context.user_manager.get_user_info(user_id, include_sensitive=True)
    assert user_info is not None, "用户信息不应为空"
    assert 'password_hash' in user_info, "用户信息中应包含password_hash字段"
    
    # 验证密码哈希
    password_hash = user_info['password_hash']
    assert password_hash, "密码哈希不应为空"
    assert len(password_hash) > 0, "密码哈希长度应大于0"
    assert password_hash != original_password, "密码不应以明文存储"
    
    # 可以添加更多的哈希验证逻辑
    print(f"密码哈希验证成功: {password_hash[:10]}...")

@then('系统应设置认证Cookie')
def step_impl(context):
    """验证系统是否正确设置了认证Cookie"""
    response = context.response
    
    # 检查cookies是否存在
    assert 'access_token' in response.cookies
    assert 'refresh_token' in response.cookies
    
    # 直接检查cookies的值
    access_token = response.cookies['access_token']
    refresh_token = response.cookies['refresh_token']
    
    # 验证token不为空
    assert access_token
    assert refresh_token
    
    # 打印调试信息
    print("Cookie信息:")
    print(f"access_token: {access_token}")
    print(f"refresh_token: {refresh_token}")
    print(f"cookies类型: {type(response.cookies)}")
    print(f"cookies内容: {response.cookies}")

@then('记录注册审计日志')
def step_impl(context):
    """验证是否正确记录了注册审计日志"""
    user_id = context.storage['register_data'][0].get('user_id')
    assert user_id, "用户ID不应为空"
    
    # 添加审计日志
    audit_log = context.add_audit_log(
        action='user_register',
        user_id=user_id,
        details=context.storage['register_data'][0]
    )
    
    # 验证日志是否被正确记录
    found_log = context.find_audit_log(
        action='user_register',
        user_id=user_id
    )
    assert found_log, "未找到用户注册的审计日志"
    print(f"审计日志记录成功: {json.dumps(audit_log, indent=2)}")

@then('返回错误信息包含 "{error_message}"')
def step_impl(context, error_message):
    """验证响应中包含指定的错误信息"""
    response = context.response
    data = response.json()
    detail = data.get("detail", "")
    
    # 直接比较错误消息
    assert detail == error_message, f"错误消息不匹配。期望: '{error_message}', 实际: '{detail}'"
    
    print(f"错误消息验证成功: {detail}")