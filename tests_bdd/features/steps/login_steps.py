from behave import given, when, then
from fastapi import Response, HTTPException
from fastapi.testclient import TestClient
import json

@given('系统已有注册用户')
def step_impl(context):
    """创建测试用户"""
    form_data = {row['字段']: row['值'] for row in context.table}
    
    response = context.client.post(
        "/api/auth/register",
        data=form_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    context.response = response
    
    assert response.status_code == 200
    print(f"创建测试用户: {form_data['username']}")

@when('用户登录到设备')
def step_impl(context):
    """使用特性文件中的示例数据登录"""
    # 获取登录数据
    form_data = {row["字段"]: row["值"] for row in context.table}
    print(">>> form_data: ", form_data)
    
    # 发送登录请求
    response = context.client.post(
        "/api/auth/login",
        data=form_data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )
    
    # 保存响应和状态码
    context.response = response
    context.status_code = response.status_code
    
    # 验证响应
    assert response.status_code == 200, f"Login failed with status {response.status_code}"
    
    # 一次性设置所有 cookies
    context.client.cookies.clear()  # 先清除旧的 cookies
    for cookie in response.cookies.items():
        name, value = cookie
        context.client.cookies.set(name, value)
    
    print(">>> Client cookies after login:", model_dump(context.client.cookies))

@when('系统验证用户凭据')
def step_impl(context):
    """验证系统正确验证了用户凭据"""
    response = context.response.json()
    assert response['data']['user_info']
    context.user_info = response['data']['user_info']

@then('用户凭据应验证成功')
def step_impl(context):
    """验证系统正确验证了用户凭据"""
    response = context.response.json()
    print(">>> login response: ", response)
    assert response['data']['user_info']
    context.user_info = response['data']['user_info']

@then('返回成功响应，包含')
def step_impl(context):
    """验证返回的数据结构符合API文档"""
    data = context.response.json()['data']
    
    # 验证所有必需字段存在且类型正确
    for row in context.table:
        field = row['字段']
        expected_type = row['类型']
        
        assert field in data, f"响应中缺少字段: {field}"
        
        if expected_type == 'boolean':
            assert isinstance(data[field], bool), f"{field} 应该是布尔类型"
        elif expected_type == 'object':
            assert isinstance(data[field], dict), f"{field} 应该是对象类型"

@then('HTTP响应存在认证令牌')
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

@then('服务端应存在用户的令牌')
def step_impl(context):
    """验证服务端存在同一个用户的令牌"""
    data = {row['字段']: row['值'] for row in context.table}
    
    # 获取用户的设备列表
    user_id = context.user_info["user_id"]
    result = context.tokens_manager.list_user_devices(user_id)
    print(">>> list_user_devices: ", result.data)
    
    # 验证响成功
    assert result.success is True, "获取设备列表失败"
    assert result.data is not None, "设备列表为空"
    
    # 验证设备列表中包含表格中指定的所有设备
    device_ids = result.data
    for row in context.table:
        if row['字段'] == 'device_id':
            print(">>> 验证设备：", row['值'], "是否在列表中", device_ids)
            assert row['值'] in device_ids, f"未找到设备 {row['值']}"

@then('服务端不应存在用户的令牌')
def step_impl(context):
    """验证服务端不存在用户的令牌"""
    data = {row['字段']: row['值'] for row in context.table}
    
    # 获取用户的设备列表
    user_id = context.user_info["user_id"]
    result = context.tokens_manager.list_user_devices(user_id)
    print(">>> list_user_devices: ", result.data)
    
    # 验证响成功
    assert result.success is True, "获取设备列表失败"
    
    # 验证设备列表中包含表格中指定的所有设备
    device_ids = result.data
    for row in context.table:
        if row['字段'] == 'device_id':
            print(">>> 验证设备：", row['值'], "是否不在列表中", device_ids)
            assert row['值'] not in device_ids, f"找到设备 {row['值']}"

@when('用户在最近使用的设备上退出登录')
def step_impl(context):
    """发送登出请求"""
    # 获取最后一次登录的 cookies
    cookies = context.client.cookies
    
    # 打印当前的 cookies 用于调试
    print(">>> Current cookies:", model_dump(cookies))
    
    # 确保有认证信息
    assert "refresh_token" in cookies, "No refresh token found in cookies"
    assert "access_token" in cookies, "No access token found in cookies"
    assert "device_id" in cookies, "No device_id found in cookies"
    
    # 发送登出请求，带上所有 cookies
    response = context.client.post(
        "/api/auth/logout-device",
    )

    # 打印响应信息用于调试
    print(">>> Logout Response Status Code:", response.status_code)
    print(">>> Logout Response Content:", response.json())

    # 断言响应状态码为 200
    assert response.status_code == 200, f"Expected status code 200, got {response.status_code}"

    # 检查响应中是否成功清除 Cookie
    assert "access_token" not in response.cookies, "Access token should be cleared"
    assert "refresh_token" not in response.cookies, "Refresh token should be cleared"

    context.logout_response = response

@when('用户使用错误的凭据登录')
def step_impl(context):
    """使用特性文件中的示例数据登录"""
    # 获取登录数据
    form_data = {row["字段"]: row["值"] for row in context.table}
    print(">>> form_data: ", form_data)
    
    # 发送登录请求
    response = context.client.post(
        "/api/auth/login",
        data=form_data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )
    
    # 保存响应和状态码
    context.login_response = response
    context.status_code = response.status_code

@then('系统应返回401未授权错误')
def step_impl(context):
    """验证系统返回401错误"""
    response = context.login_response
    assert response.status_code == 401, f"期望状态码401，实际得到{response.status_code}"
    
    # 验证响应中没有设置认证cookie
    assert "access_token" not in response.cookies
    assert "refresh_token" not in response.cookies
    
    print(f"Response Status Code: {response.status_code}")
    print(f"Response Cookies: {response.cookies}")

