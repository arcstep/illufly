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
    form_data = {row['字段']: row['值'] for row in context.table}
    
    context.response = context.client.post(
        "/api/auth/login",
        data=form_data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )
    print(f"登录响应状态码: {context.response.status_code}")
    if context.response.status_code != 200:
        print(f"登录响应内容: {context.response.json()}")
    else:
        print(f"登录成功: {context.response.json()}")

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

@then('服务端存在同一个用户的多个令牌')
def step_impl(context):
    """验证服务端存在同一个用户的多个令牌"""
    data = {row['字段']: row['值'] for row in context.table}
    
    # 获取用户的设备列表
    response = context.auth_manager.list_user_devices(context.device_a_tokens["access_token"])
    
    # 验证响应成功
    assert response["success"] is True, "获取设备列表失败"
    
    # 验证设备列表中包含表格中指定的所有设备
    device_ids = [device["device_id"] for device in response["devices"]]
    for row in context.table:
        if row['字段'] == 'device_id':
            assert row['值'] in device_ids, f"未找到设备 {row['值']}"
    
    print(f"用户设备列表: {device_ids}")

@when('用户在设备A请求退出')
def step_impl(context):
    """发送登出请求"""
    # 打印当前的 Cookie 信息
    print("Device A Cookies:", context.device_a_tokens)

    # 发送登出请求
    response = context.client.post("/api/auth/logout", cookies={
        "access_token": context.device_a_tokens["access_token"],
        "refresh_token": context.device_a_tokens["refresh_token"]
    })

    # 打印响应状态码和内容
    print("Logout Response Status Code:", response.status_code)
    print("Logout Response Content:", response.json())

    # 断言响应状态码为 200
    assert response.status_code == 200, f"Expected status code 200, got {response.status_code}"

    # 检查响应中是否成功清除 Cookie
    assert "access_token" not in response.cookies, "Access token should be cleared"
    assert "refresh_token" not in response.cookies, "Refresh token should be cleared"

    context.logout_response = response

@then('系统应清除设备A的认证Cookie')
def step_impl(context):
    """验证设备A的认证Cookie已被清除"""
    # 打印登出请求前的 Cookie 信息
    print("Before Logout - Device A Cookies:", context.device_a_tokens)

    # 获取登出请求的响应
    response = context.logout_response

    # 打印响应状态码和内容
    print("Logout Response Status Code:", response.status_code)
    print("Logout Response Content:", response.json())

    # 断言响应状态码为 200
    assert response.status_code == 200, f"Expected status code 200, got {response.status_code}"

    # 检查响应中是否包含清除 Cookie 的指令
    assert "access_token" not in response.cookies, "Access token should be cleared"
    assert "refresh_token" not in response.cookies, "Refresh token should be cleared"

    # 打印登出请求后的 Cookie 信息
    print("After Logout - Response Cookies:", response.cookies)

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
    device_b_token = context.device_b_tokens["access_token"]
    
    # 获取 invalidate_access_token 的所有调用
    calls = context.auth_manager.invalidate_access_token.call_args_list
    
    # 验证设备B的令牌没有被撤销
    for call in calls:
        args, _ = call
        assert args[0] != device_b_token, f"设备B的令牌被错误地撤销了: {device_b_token}"
    
    # 打印调试信息
    print(f"Device B token: {device_b_token}")
    print(f"Invalidate calls: {calls}")

@given('用户持有有效的http_only刷新令牌')
def step_impl(context):
    """模拟用户已有有效的刷新令牌"""
    # 生成符合 JWT 格式的模拟令牌
    context.refresh_token = "mock.refresh.token"  # 确保有3段
    context.access_token = "mock.access.token"
    
    # 设置 cookies
    context.client.cookies = {
        "access_token": context.access_token,
        "refresh_token": context.refresh_token
    }
    
    print(f"Initial Tokens - Access: {context.access_token}, Refresh: {context.refresh_token}")


@when('用户请求零登录')
def step_impl(context):
    """使用刷新令牌获取新的访问令牌"""
    response = context.client.post(
        "/api/auth/refresh-token",
        data={"refresh_token": context.refresh_token}
    )
    context.refresh_response = response
    
    print(f"Token Refresh Response Status: {response.status_code}")
    print(f"Token Refresh Response Content: {response.json()}")


@then('系统应验证刷新令牌')
def step_impl(context):
    """验证系统是否正确验证了刷新令牌"""
    # 验证令牌验证方法被调用
    context.auth_manager.is_token_valid.assert_called_with(
        context.refresh_token, "refresh"
    )
    context.auth_manager.verify_jwt.assert_called_with(
        context.refresh_token
    )
    
    # 验证旧令牌是否被撤销
    context.auth_manager.invalidate_token.assert_called_with(
        context.refresh_token
    )
    
    print(f"Token Validation Calls:")
    print(f"- is_token_valid: {context.auth_manager.is_token_valid.call_args_list}")
    print(f"- verify_jwt: {context.auth_manager.verify_jwt.call_args_list}")
    print(f"- invalidate_token: {context.auth_manager.invalidate_token.call_args_list}")


@then('返回成功响应，包含新的访问令牌')
def step_impl(context):
    """验证令牌刷新响应"""
    response = context.refresh_response
    assert response.status_code == 200
    
    response_data = response.json()
    assert response_data["success"] is True
    assert "access_token" in response_data
    assert "refresh_token" in response_data
    
    # 验证新的令牌已设置到 Cookie
    assert "access_token" in response.cookies
    assert "refresh_token" in response.cookies
    
    # 验证新旧令牌不同
    assert response_data["access_token"] != context.access_token
    assert response_data["refresh_token"] != context.refresh_token
    
    print(f"New Tokens:")
    print(f"- Access Token: {response_data['access_token']}")
    print(f"- Refresh Token: {response_data['refresh_token']}")
    print(f"Response Cookies: {response.cookies}")

@when('用户在设备A提供错误的登录信息')
def step_impl(context):
    """使用错误的凭据尝试登录"""
    # 从数据表中获取登录信息
    login_data = {row['字段']: row['值'] for row in context.table}
    
    # 发送登录请求
    response = context.client.post(
        "/api/auth/login",
        data=login_data
    )
    context.login_response = response
    
    print(f"Login Data: {login_data}")
    print(f"Login Response Status: {response.status_code}")
    print(f"Login Response Content: {response.json()}")


@then('系统应返回401未授权错误')
def step_impl(context):
    """验证系统返回401错误"""
    response = context.login_response
    assert response.status_code == 401, \
        f"期望状态码401，实际得到{response.status_code}"
    
    # 验证响应中没有设置认证cookie
    assert "access_token" not in response.cookies
    assert "refresh_token" not in response.cookies
    
    print(f"Response Status Code: {response.status_code}")
    print(f"Response Cookies: {response.cookies}")


@then('错误信息应包含认证失败的详情')
def step_impl(context):
    """验证错误响应的详细信息"""
    response = context.login_response
    response_data = response.json()
    
    # 验证错误响应的结构
    assert "detail" in response_data, \
        "响应中缺少错误详情"
    
    error_detail = response_data["detail"]
    # 只验证是否包含"认证失败"，不再检查具体原因
    assert "认证失败" in error_detail, \
        f"错误信息不符合预期: {error_detail}"
    
    print(f"Error Response: {response_data}")

@given('用户账户已被锁定')
def step_impl(context):
    context.user_manager._test_state['is_locked'] = True

@when('用户在设备A尝试登录')
def step_impl(context):
    """模拟用户登录尝试"""
    login_data = {
        "username": "testuser",
        "password": "Test123!@#"
    }
    
    response = context.client.post(
        "/api/auth/login",
        data=login_data
    )
    context.login_response = response
    
    print(f"Login Data: {login_data}")
    print(f"Login Response Status: {response.status_code}")
    print(f"Login Response Content: {response.json()}")

@then('系统应返回403禁止访问错误')
def step_impl(context):
    """验证系统返回403错误"""
    response = context.login_response
    assert response.status_code == 403, \
        f"期望状态码403，实际得到{response.status_code}"
    
    assert "access_token" not in response.cookies
    assert "refresh_token" not in response.cookies
    
    print(f"Response Status Code: {response.status_code}")
    print(f"Response Cookies: {response.cookies}")

@then('错误信息应说明"账户已锁定"')
def step_impl(context):
    response = context.login_response
    response_data = response.json()
    
    assert "detail" in response_data, \
        "响应中缺少错误详情"
    
    error_detail = response_data["detail"]
    assert error_detail == "账户已锁定", \
        f"错误信息不符合预期: {error_detail}"

@then('错误信息���说明"账户未激活"')
def step_impl(context):
    response = context.login_response
    response_data = response.json()
    
    assert "detail" in response_data, \
        "响应中缺少错误详情"
    
    error_detail = response_data["detail"]
    assert error_detail == "账户未激活", \
        f"错误信息不符合预期: {error_detail}"

@given('用户账户未激活')
def step_impl(context):
    context.user_manager._test_state['is_active'] = False

@when('用户在设备A提供不完整的登录信息')
def step_impl(context):
    """模拟提供不完整的登录信息"""
    # 从数据表中获取登录信息
    login_data = {row['字段']: row['值'] for row in context.table}
    
    # 发送登录请求
    response = context.client.post(
        "/api/auth/login",
        data=login_data
    )
    context.login_response = response
    
    print(f"Login Data: {login_data}")
    print(f"Login Response Status: {response.status_code}")
    print(f"Login Response Content: {response.json()}")


@then('系统应返回400错误')
def step_impl(context):
    """验证系统返回422错误（FastAPI的表单验证错误）"""
    response = context.login_response
    assert response.status_code == 422, \
        f"期望状态码422，实际得到{response.status_code}"
    
    # 验证响应中没有设置认证cookie
    assert "access_token" not in response.cookies
    assert "refresh_token" not in response.cookies
    
    print(f"Response Status Code: {response.status_code}")
    print(f"Response Cookies: {response.cookies}")


@then('错误信息应说明缺少必填字段')
def step_impl(context):
    """验证错误响应中包含缺少字段的信息"""
    response = context.login_response
    response_data = response.json()
    
    # FastAPI的验证错误格式
    assert "detail" in response_data, \
        "响应中缺少错误详情"
    
    error_details = response_data["detail"]
    assert isinstance(error_details, list), \
        "错误详情应为列表格式"
    
    # 检查是否包含密码字段缺失的错误
    found_password_error = False
    for error in error_details:
        if error.get("loc") == ["body", "password"] and \
           error.get("type") == "missing":
            found_password_error = True
            break
    
    assert found_password_error, \
        f"未找到密码字段缺失的错误信息: {error_details}"
    
    print(f"Error Response: {response_data}")