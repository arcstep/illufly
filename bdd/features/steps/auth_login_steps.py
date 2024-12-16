from behave import given, when, then
from fastapi import Response, HTTPException
import json

TEST_USER = {
    'username': 'testuser',
    'password': 'Test123!@#',
    'email': 'test@example.com'
}

@given('系统已有注册用户')
def step_impl(context):
    """创建测试用户"""
    # 清理可能存在的用户
    context.storage.clear_all()
    
    # 注册用户
    response = context.client.post(
        "/api/auth/register",
        data=TEST_USER
    )
    assert response.status_code == 200
    print(f"创建测试用户: {TEST_USER['username']}")

@when('用户在设备A提供正确的登录信息')
def step_impl(context):
    """使用特性文件中的示例数据登录"""
    form_data = {}
    for row in context.table:
        form_data[row['Field']] = row['Value']
    
    # 使用 Form 数据格式发送请求
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    try:
        context.response = context.client.post(
            "/api/auth/login",
            data=form_data,
            headers=headers
        )
        print(f"登录响应状态码: {context.response.status_code}")
        if context.response.status_code != 200:
            print(f"登录响应内容: {context.response.json()}")
        else:
            print(f"登录成功: {context.response.json()}")
    except HTTPException as e:
        context.response = type('Response', (), {
            'status_code': e.status_code,
            'json': lambda: {"detail": e.detail}
        })

@then('系统应验证用户凭据')
def step_impl(context):
    """验证系统正确验证了用户凭据"""
    assert context.response.status_code == 200
    data = context.response.json()
    assert data["success"] is True

@then('返回成功响应，包含')
def step_impl(context):
    """验证返回的数据结构符合API文档"""
    data = context.response.json()
    
    # 验证所有必需字段存在且类型正确
    for row in context.table:
        field = row['Field']
        expected_type = row['Type']
        
        assert field in data, f"响应中缺少字段: {field}"
        
        if expected_type == 'boolean':
            assert isinstance(data[field], bool), f"{field} 应该是布尔类型"
        elif expected_type == 'object':
            assert isinstance(data[field], dict), f"{field} 应该是对象类型"

@then('设置设备A的认证Cookie')
def step_impl(context):
    """验证设备A的Cookie设置"""
    response = context.response
    
    # 从响应头获取所有Set-Cookie
    set_cookie_headers = response.headers.get_list('set-cookie')
    
    # 解析Cookie属性
    cookies = {}
    for header in set_cookie_headers:
        parts = header.split(';')
        cookie_parts = parts[0].split('=')
        cookie_name = cookie_parts[0].strip()
        cookie_value = cookie_parts[1].strip()
        
        attributes = {}
        for part in parts[1:]:
            if '=' in part:
                key, value = part.split('=')
                attributes[key.strip().lower()] = value.strip()
            else:
                attributes[part.strip().lower()] = True
                
        cookies[cookie_name] = attributes
    
    # 验证必需的Cookie存在
    assert 'access_token' in cookies, "缺少访问令牌Cookie"
    assert 'refresh_token' in cookies, "缺少刷新令牌Cookie"
    
    # 验证Cookie属性
    for cookie_name in ['access_token', 'refresh_token']:
        cookie = cookies[cookie_name]
        assert 'httponly' in cookie, f"{cookie_name} 应该是httponly"
        assert 'secure' in cookie, f"{cookie_name} 应该是secure"
        assert cookie.get('samesite', '').lower() == 'lax', f"{cookie_name} 应该是samesite=lax"

@given('用户已在设备A登录')
def step_impl(context):
    """设置设备A的登录状态"""
    response = context.client.post(
        "/api/auth/login",
        data=TEST_USER
    )
    assert response.status_code == 200
    context.device_a_cookies = response.cookies

@when('用户在设备B提供正确的登录信息')
def step_impl(context):
    """使用相同的测试用户在设备B登录"""
    form_data = {
        'username': 'testuser',
        'password': 'Test123!@#'
    }
    
    # 验证表格数据
    for row in context.table:
        assert form_data[row['Field']] == row['Value']
    
    context.response = context.client.post(
        "/api/auth/login",
        data=form_data
    )

@then('设置设备B的认证Cookie')
def step_impl(context):
    """验证设备B的Cookie设置"""
    response = context.response
    cookies = response.cookies
    
    assert 'access_token' in cookies
    assert 'refresh_token' in cookies
    context.device_b_cookies = cookies

@given('用户已在设备A和设备B登录')
def step_impl(context):
    """设置两个设备的登录状态"""
    # 设备A登录
    response = context.client.post(
        "/api/auth/login",
        data={
            "username": TEST_USER["username"],
            "password": TEST_USER["password"]
        },
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )
    assert response.status_code == 200
    context.device_a_cookies = response.cookies
    
    # 设备B登录
    response = context.client.post(
        "/api/auth/login",
        data={
            "username": TEST_USER["username"],
            "password": TEST_USER["password"]
        },
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )
    assert response.status_code == 200
    context.device_b_cookies = response.cookies

@when('用户在设备A请求退出')
def step_impl(context):
    """发送登出请求"""
    # 设置模拟的令牌
    access_token = "mock_access_token_A"
    refresh_token = "mock_refresh_token_A"
    
    # 设置认证Cookie
    cookies = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "device_id": "device_A"
    }
    
    # 发送登出请求
    response = context.client.post(
        "/api/auth/logout",
        cookies=cookies
    )
    
    # 保存响应和令牌信息以供后续步骤使用
    context.logout_response = response
    context.device_a_tokens = {
        "access_token": access_token,
        "refresh_token": refresh_token
    }

@then('系统应清除设备A的认证Cookie')
def step_impl(context):
    """验证设备A的令牌已被撤销且Cookie已被清除"""
    response = context.logout_response
    assert response.status_code == 200, f"退出登录失败: {response.status_code} - {response.json()}"
    
    # 验证访问令牌被撤销
    context.auth_manager.invalidate_access_token.assert_called_with(
        context.device_a_tokens["access_token"]
    )
    
    # 验证刷新令牌被撤销
    context.auth_manager.invalidate_refresh_token.assert_called_with(
        context.device_a_tokens["refresh_token"]
    )
    
    # 验证响应中的Cookie已被删除
    cookies = response.cookies
    assert "access_token" not in cookies or cookies["access_token"] == "", "访问令牌未被清除"
    assert "refresh_token" not in cookies or cookies["refresh_token"] == "", "刷新令牌未被清除"
    
    # 验证响应内容
    response_data = response.json()
    assert response_data["success"] is True, "登出响应不成功"
    assert "message" in response_data, "登出响应缺少消息"

@then('设备B的令牌仍然有效')
def step_impl(context):
    """验证设备B的令牌未被撤销"""
    # 验证设备B的令牌未被撤销
    context.auth_manager.invalidate_access_token.assert_not_called_with(
        "mock_access_token_B"
    )
    context.auth_manager.invalidate_refresh_token.assert_not_called_with(
        "mock_refresh_token_B"
    )
    
    # 使用设备B的Cookie发送请求验证其仍然有效
    cookies = {
        "access_token": "mock_access_token_B",
        "refresh_token": "mock_refresh_token_B",
        "device_id": "device_B"
    }
    
    response = context.client.get(
        "/api/auth/user/info",
        cookies=cookies
    )
    
    assert response.status_code == 200, "设备B的令牌已失效"