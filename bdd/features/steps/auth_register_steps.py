# features/steps/auth_register_steps.py
from behave import given, when, then
from fastapi import Response
import json

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
    context.storage.clear_all()
    print("清理测试数据完成")

@given('存在用户名 "{username}"')
def step_impl(context, username):
    print(f"模拟已存在用户: {username}")
    context.existing_users.add(username)

@when('提交用户注册请求')
def step_impl(context):
    form_data = {}
    for row in context.table:
        field = row['字段']
        value = row['值']
        form_data[field] = value
    
    print(f"提交注册表单数据: {form_data}")
    context.form_data = form_data  # 保存到context以供后续步骤使用
    context.response = context.client.post(
        "/api/auth/register",
        data=form_data,
        allow_redirects=True  # 允许重定向
    )
    print(f"API响应状态码: {context.response.status_code}")

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
    data = context.response.json()
    user_id = data["user_info"]["user_id"]
    stored_password = context.storage.get_password_hash(user_id)
    assert stored_password.startswith("$argon2id$")
    print("密码已使用 Argon2id 安全存储")

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
    data = context.response.json()
    user_id = data["user_info"]["user_id"]
    audit_log = context.storage.get_audit_log(
        action="user_register",
        user_id=user_id
    )
    assert audit_log is not None
    print(f"已记录注册审计日志: {audit_log}")

@then('返回错误信息包含 "{error_message}"')
def step_impl(context, error_message):
    data = context.response.json()
    assert error_message in data["detail"]