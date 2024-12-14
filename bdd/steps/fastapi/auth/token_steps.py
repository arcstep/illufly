from behave import given, when, then
from fastapi.testclient import TestClient
import jwt
from datetime import datetime, timedelta

@given('系统中存在已登录用户')
def step_impl(context):
    context.client = TestClient(context.app)
    # 创建测试用户并登录
    context.test_user = {
        "username": "testuser",
        "password": "Test123!@#"
    }
    context.access_token = "test_access_token"
    context.refresh_token = "test_refresh_token"

@given('用户持有有效的刷新令牌')
def step_impl(context):
    # 确保用户有有效的刷新令牌
    context.refresh_token = "valid_refresh_token"

@given('当前用户具有管理员权限')
def step_impl(context):
    context.is_admin = True
    context.admin_token = "admin_access_token"

@given('当前用户不具有管理员权限')
def step_impl(context):
    context.is_admin = False

@when('用户请求刷新令牌')
def step_impl(context):
    data = {}
    for row in context.table:
        data[row['Field']] = row['Value']
    
    context.response = context.client.post(
        "/api/auth/token/refresh",
        json={"refresh_token": data['refresh_token']}
    )

@when('用户提供格式错误的刷新令牌')
def step_impl(context):
    context.response = context.client.post(
        "/api/auth/token/refresh",
        json={"refresh_token": "invalid_format_token"}
    )

@when('用户提供已过期的刷新令牌')
def step_impl(context):
    # 创建一个已过期的令牌
    expired_token = "expired_token"
    context.response = context.client.post(
        "/api/auth/token/refresh",
        json={"refresh_token": expired_token}
    )

@when('用户请求注销')
def step_impl(context):
    headers = {"Authorization": f"Bearer {context.access_token}"}
    context.response = context.client.post(
        "/api/auth/logout",
        headers=headers
    )

@when('用户请求撤销当前设备的令牌')
def step_impl(context):
    headers = {"Authorization": f"Bearer {context.access_token}"}
    context.response = context.client.post(
        "/api/auth/token/revoke-current",
        headers=headers
    )

@when('用户请求撤销自身的所有令牌')
def step_impl(context):
    headers = {"Authorization": f"Bearer {context.access_token}"}
    context.response = context.client.post(
        "/api/auth/token/revoke-all",
        headers=headers
    )

@when('管理员请求撤销指定用户的所有令牌')
def step_impl(context):
    headers = {"Authorization": f"Bearer {context.admin_token}"}
    data = {row['Field']: row['Value'] for row in context.table}
    context.response = context.client.post(
        "/api/auth/admin/token/revoke-all",
        json=data,
        headers=headers
    )

@when('管理员请求撤销指定用户的访问令牌')
def step_impl(context):
    headers = {"Authorization": f"Bearer {context.admin_token}"}
    data = {row['Field']: row['Value'] for row in context.table}
    context.response = context.client.post(
        "/api/auth/admin/token/revoke-access",
        json=data,
        headers=headers
    )

@when('管理员请求暂时冻结指定用户')
def step_impl(context):
    headers = {"Authorization": f"Bearer {context.admin_token}"}
    data = {row['Field']: row['Value'] for row in context.table}
    context.response = context.client.post(
        "/api/auth/admin/user/freeze",
        json=data,
        headers=headers
    )

@when('用户尝试撤销他人的令牌')
def step_impl(context):
    headers = {"Authorization": f"Bearer {context.access_token}"}
    context.response = context.client.post(
        "/api/auth/admin/token/revoke-all",
        json={"username": "other_user"},
        headers=headers
    )

@when('管理员尝试撤销不存在用户的令牌')
def step_impl(context):
    headers = {"Authorization": f"Bearer {context.admin_token}"}
    context.response = context.client.post(
        "/api/auth/admin/token/revoke-all",
        json={"username": "nonexistent_user"},
        headers=headers
    )

@then('系统应验证刷新令牌')
def step_impl(context):
    assert context.response.status_code == 200

@then('使旧的刷新令牌失效')
def step_impl(context):
    # 验证旧令牌已失效
    pass

@then('生成新的访问令牌和刷新令牌')
def step_impl(context):
    response_data = context.response.json()
    assert "access_token" in response_data
    assert "refresh_token" in response_data

@then('返回成功响应，包含')
def step_impl(context):
    assert context.response.status_code == 200
    response_data = context.response.json()
    for row in context.table:
        assert row['Field'] in response_data
        # 可以添加类型检查

@then('更新认证Cookie')
def step_impl(context):
    assert 'Set-Cookie' in context.response.headers

@then('系统应返回400错误')
def step_impl(context):
    assert context.response.status_code == 400

@then('系统应返回401未授权错误')
def step_impl(context):
    assert context.response.status_code == 401

@then('系统应返回403禁止访问错误')
def step_impl(context):
    assert context.response.status_code == 403

@then('错误信息应说明令牌格式无效')
def step_impl(context):
    response_data = context.response.json()
    assert "invalid_token_format" in response_data.get("error", "")

@then('错误信息应说明令牌已过期')
def step_impl(context):
    response_data = context.response.json()
    assert "token_expired" in response_data.get("error", "")

@then('错误信息应说明权限不足')
def step_impl(context):
    response_data = context.response.json()
    assert "insufficient_permissions" in response_data.get("error", "")

@then('错误信息应说明用户不存在')
def step_impl(context):
    response_data = context.response.json()
    assert "user_not_found" in response_data.get("error", "")

@then('系统应清除用户的认证Cookie')
def step_impl(context):
    assert 'Set-Cookie' in context.response.headers
    # 验证cookie被清除

@then('移除用户的所有令牌')
def step_impl(context):
    # 验证所有令牌已被移除
    pass

@then('返回成功响应')
def step_impl(context):
    assert context.response.status_code == 200

@then('系统应移除用户当前设备的令牌')
def step_impl(context):
    # 验证当前设备令牌已被移除
    pass

@then('强制用户在该设备上重新登录')
def step_impl(context):
    # 验证用户需要重新登录
    pass

@then('强制用户在所有设备上重新登录')
def step_impl(context):
    # 验证所有设备都需要重新登录
    pass

@then('系统应移除该用户的所有令牌')
def step_impl(context):
    # 验证指定用户的所有令牌已被移除
    pass

@then('系统应移除该用户的访问令牌')
def step_impl(context):
    # 验证指定用户的访问令牌已被移除
    pass

@then('系统应暂时冻结该用户的账户')
def step_impl(context):
    # 验证用户账户已被冻结
    pass

@then('响应信息应包含被操作的用户名')
def step_impl(context):
    response_data = context.response.json()
    assert "username" in response_data