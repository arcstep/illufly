# features/steps/auth_register_steps.py
from behave import given, when, then
from fastapi import Response
from datetime import datetime
import json

@given('准备好用户表单')
def step_impl(context):
    context.registration_table = context.table
    print(f"准备注册表单数据: {context.registration_table}")

@when('提交用户注册请求')
def step_impl(context): 
    """
    提交用户注册请求
    将注册数据写入到 context.register_data 和 context.users 中
    """
    context.register_data = []
    context.users = []
    # 将表格数据转换为表单数据
    form_data = {row['字段']: row['值'] for row in context.registration_table}

    # 如果邀请码为 AUTO_FIND_VALID_CODE，则自动找到第一个有效的邀请码
    if form_data.get('invite_code', '') == 'AUTO_FIND_VALID_CODE':
        assert len(context.invite_codes) > 0, "没有有效的邀请码"
        form_data['invite_code'] = context.invite_codes[0].invite_code
        form_data['invite_from'] = context.invite_codes[0].invite_from
    
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
            context.register_data.append(user_info)
            context.users.append(user_info)
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

@then('返回错误信息包含 "{error_message}"')
def step_impl(context, error_message):
    """验证响应中包含指定的错误信息"""
    response = context.response
    data = response.json()
    detail = data.get("detail", "")
    
    # 直接比较错误消息
    assert detail == error_message, f"错误消息不匹配。期望: '{error_message}', 实际: '{detail}'"
    
    print(f"错误消息验证成功: {detail}")

@given('准备好邀请码')
def step_impl(context):
    form_data = {row['字段']: row['值'] for row in context.table}
    print(f"准备邀请码数据: {form_data}")
    im = context.users_manager.invite_manager
    count = int(form_data['invite_count'])
    owner_id = form_data['invite_from']

    assert context.users_manager.invite_manager._storage._data_dir, "邀请码存储目录不存在"
    context.invite_codes = im.generate_new_invite_codes(
        count=count,
        owner_id=owner_id
    )
    print(f"生成的邀请码: {context.invite_codes}")
    assert len(context.invite_codes) == count
