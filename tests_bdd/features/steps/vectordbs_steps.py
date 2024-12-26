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
    response_data = context.response.json()
    
    # 验证响应数据包含表格中指定的字段和类型
    for row in context.table:
        field = row['字段']
        expected_type = row['类型']
        
        # 确保字段存在
        assert field in response_data, f"响应中缺少字段 {field}"
        
        # 验证字段类型
        if expected_type == 'boolean':
            assert isinstance(response_data[field], bool), f"{field} 应该是布尔类型"
        elif expected_type == 'object':
            assert isinstance(response_data[field], dict), f"{field} 应该是对象类型"
        elif expected_type == 'string':
            assert isinstance(response_data[field], str), f"{field} 应该是字符串类型"
        elif expected_type == 'integer':
            assert isinstance(response_data[field], int), f"{field} 应该是整数类型"


@then(u'指定知识库应出现在知识库列表中')
def step_impl(context):
    """验证知识库是否出现在用户的知识库列表中"""
    form_data = {row['字段']: row['值'] for row in context.table}

    # 发送GET请求获取知识库列表
    response = context.client.get("/api/vectordbs")
    # 验证请求成功
    assert response.status_code == 200, f"获取知识库列表失败: {response.text}"
    
    # 解析响应数据
    response_data = response.json()
    print(">>> vdb list:", response_data)
    
    # 获取知识库列表
    vectordbs = response_data["data"]
    print(">>> vectordbs", vectordbs)
    assert isinstance(vectordbs, list), "知识库列表应该是一个数组"
    assert form_data['name'] in vectordbs, f"新创建的知识库未在列表中。当前列表: {vectordbs}"

@then(u'可以获取指定知识库详情')
def step_impl(context):
    form_data = {row['字段']: row['值'] for row in context.table}

    response = context.client.get(f"/api/vectordbs/{form_data['name']}")
    context.response = response
    print(">>> vdb detail:", response.json())
    assert response.status_code == 200, f"获取知识库详情失败: {response.text}"
    assert response.json()["data"]["db_name"] == form_data['name'], f"获取的知识库名称不匹配。期望: {form_data['name']}, 实际: {response.json()['data']['db_name']}"
