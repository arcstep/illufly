from behave import given, when, then
from fastapi.testclient import TestClient

@given('系统处于可注册状态')
def step_impl(context):
    # 确保系统配置允许注册
    context.client = TestClient(context.app)
    # 可以在这里添加其他必要的系统状态检查

@given('当前用户具有管理员权限')
def step_impl(context):
    # 设置管理员权限
    context.is_admin = True
    # 这里可能需要创建管理员token或session

@when('用户提供以下注册信息')
def step_impl(context):
    registration_data = {}
    for row in context.table:
        registration_data[row['Field']] = row['Value']
    
    context.response = context.client.post("/api/auth/register", json=registration_data)

@when('管理员提供以下注册信息')
def step_impl(context):
    registration_data = {}
    for row in context.table:
        registration_data[row['Field']] = row['Value']
    
    # 添加管理员token到请求头
    headers = {"Authorization": "Bearer admin_token"}  # 需要替换为实际的token
    context.response = context.client.post(
        "/api/auth/admin/register", 
        json=registration_data,
        headers=headers
    )

@then('系统应创建新用户账户')
def step_impl(context):
    assert context.response.status_code == 201
    response_data = context.response.json()
    assert "user_id" in response_data

@then('返回成功响应')
def step_impl(context):
    assert context.response.status_code in [200, 201]

@then('自动登录用户')
def step_impl(context):
    response_data = context.response.json()
    assert "access_token" in response_data

@then('系统应生成随机密码并通过邮件发送给用户')
def step_impl(context):
    # 验证邮件发送逻辑
    assert context.response.status_code == 201
    # 这里需要mock邮件服务并验证是否调用

@then('系统应生成随机密码并通过手机号码发送给用户')
def step_impl(context):
    # 验证短信发送逻辑
    assert context.response.status_code == 201
    # 这里需要mock短信服务并验证是否调用

@then('系统应发送验证邮件到用户邮箱')
def step_impl(context):
    assert context.response.status_code == 202
    # 验证邮件验证流程已启动

@then('用户点击验证链接后系统应创建新用户账户')
def step_impl(context):
    # 模拟用户点击验证链接
    verification_token = context.response.json().get("verification_token")
    response = context.client.get(f"/api/auth/verify-email/{verification_token}")
    assert response.status_code == 200

@then('系统应发送验证短信到用户手机')
def step_impl(context):
    assert context.response.status_code == 202
    # 验证短信验证流程已启动

@then('用户输入短信验证码后系统应创建新用户账户')
def step_impl(context):
    # 模拟用户输入验证码
    verification_code = "123456"  # 这应该是从response中获取的mock验证码
    response = context.client.post(
        "/api/auth/verify-phone",
        json={"verification_code": verification_code}
    )
    assert response.status_code == 200