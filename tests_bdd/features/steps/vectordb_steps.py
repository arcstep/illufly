from behave import given, when, then
from fastapi import Response

@when(u'用户创建新的知识库')
def step_impl(context):
    form_data = {row['字段']: row['值'] for row in context.table}
    response = context.client.post(
        "/api/vectordbs",
        data=form_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    context.response = response
    
    # 从响应中提取 user_id
    if response.status_code == 200:
        response_data = response.json()
        print(">>> response_data", response_data)
    else:
        print(f"请求失败，状态码: {response.status_code}")
        if response.content:
            print(f"错误信息: {response.content.decode()}")

@then(u'创建应该成功')
def step_impl(context):
    assert context.response.status_code == 200, f"创建失败，状态码: {context.response.status_code}"

@then(u'返回的数据应包含')
def step_impl(context):
    raise NotImplementedError(u'STEP: Then 返回的数据应包含')


@then(u'知识库应出现在用户的知识库列表中')
def step_impl(context):
    raise NotImplementedError(u'STEP: Then 知识库应出现在用户的知识库列表中')
