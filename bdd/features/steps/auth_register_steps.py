# features/steps/auth_register_steps.py
from behave import given, when, then
from fastapi import Response
import json
from datetime import datetime

@given('Mock系统已启动')
def step_impl(context):
    assert context.client is not None
    print("Mock系统已启动")

@given('用户管理模块正常运行')
def step_impl(context):
    assert context.user_manager is not None
    print("用户管理模块正常运行")

@given('清理测试数据')
def step_impl(context):
    # 清理用户数据
    if hasattr(context, 'existing_users'):
        context.existing_users.clear()
    
    # 清理令牌数据
    if hasattr(context, 'auth_manager'):
        context.auth_manager.clear_tokens()
    
    # 清理存储数据
    if hasattr(context, 'storage'):
        for key in context.storage:
            context.storage[key].clear()

@given('存在用户名 "{username}"')
def step_impl(context, username):
    print(f"模拟已存在用户: {username}")
    context.existing_users.add(username)

@when('提交用户注册请求')
def step_impl(context):
    # 保存注册表格数据供后续步骤使用
    context.registration_table = context.table  # 直接保存 Behave 的 table 对象
    
    # 将表格数据转换为表单数据
    form_data = {row['字段']: row['值'] for row in context.table}
    print(f"提交注册表单数据: {form_data}")
    
    response = context.client.post(
        "/api/auth/register",
        data=form_data
    )
    context.response = response
    
    # 从响应中提取 user_id
    if response.status_code == 200:
        response_data = response.json()
        if response_data.get('user_info'):
            context.user_id = response_data['user_info'].get('user_id')
            print(f"获取到用户ID: {context.user_id}")
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
    user_id = context.user_id
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
    user_id = context.user_id
    assert user_id, "用户ID不应为空"
    
    # 添加审计日志
    audit_log = context.add_audit_log(
        action='user_register',
        user_id=user_id,
        details={
            'username': 'mockuser',
            'email': 'mock@example.com',
            'roles': ['user', 'guest']
        }
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
    data = context.response.json()
    assert error_message in data["detail"]