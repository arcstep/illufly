from behave import given, when, then
from fastapi import Response

@when(u'用户创建新的Agent')
def step_impl(context):
    raise NotImplementedError(u'STEP: When 用户创建新的Agent')


@then(u'Agent应出现在用户的Agent列表中')
def step_impl(context):
    raise NotImplementedError(u'STEP: Then Agent应出现在用户的Agent列表中')


@given(u'用户已创建以下Agent')
def step_impl(context):
    raise NotImplementedError(u'STEP: Given 用户已创建以下Agent')


@when(u'用户请求Agent列表')
def step_impl(context):
    raise NotImplementedError(u'STEP: When 用户请求Agent列表')


@then(u'返回的列表应包含2个Agent')
def step_impl(context):
    raise NotImplementedError(u'STEP: Then 返回的列表应包含2个Agent')


@then(u'每个Agent信息应包含')
def step_impl(context):
    raise NotImplementedError(u'STEP: Then 每个Agent信息应包含')


@given(u'存在名为"test_agent"的Agent')
def step_impl(context):
    raise NotImplementedError(u'STEP: Given 存在名为"test_agent"的Agent')


@when(u'用户更新Agent配置')
def step_impl(context):
    raise NotImplementedError(u'STEP: When 用户更新Agent配置')


@then(u'更新应该成功')
def step_impl(context):
    raise NotImplementedError(u'STEP: Then 更新应该成功')


@then(u'Agent的配置应被更新为新值')
def step_impl(context):
    raise NotImplementedError(u'STEP: Then Agent的配置应被更新为新值')


@when(u'用户发送消息"你好"')
def step_impl(context):
    raise NotImplementedError(u'STEP: When 用户发送消息"你好"')


@then(u'应建立SSE连接')
def step_impl(context):
    raise NotImplementedError(u'STEP: Then 应建立SSE连接')


@then(u'应收到Agent的回复')
def step_impl(context):
    raise NotImplementedError(u'STEP: Then 应收到Agent的回复')


@when(u'用户执行创建操作')
def step_impl(context):
    raise NotImplementedError(u'STEP: When 用户执行创建操作')


@then(u'系统应返回400')
def step_impl(context):
    raise NotImplementedError(u'STEP: Then 系统应返回400')


@then(u'错误信息应包含"Agent已存在"')
def step_impl(context):
    raise NotImplementedError(u'STEP: Then 错误信息应包含"Agent已存在"')


@when(u'用户执行更新操作')
def step_impl(context):
    raise NotImplementedError(u'STEP: When 用户执行更新操作')


@then(u'系统应返回404')
def step_impl(context):
    raise NotImplementedError(u'STEP: Then 系统应返回404')


@then(u'错误信息应包含"Agent不存在"')
def step_impl(context):
    raise NotImplementedError(u'STEP: Then 错误信息应包含"Agent不存在"')


@when(u'用户执行删除操作')
def step_impl(context):
    raise NotImplementedError(u'STEP: When 用户执行删除操作')


@when(u'用户执行对话操作')
def step_impl(context):
    raise NotImplementedError(u'STEP: When 用户执行对话操作')


@then(u'错误信息应包含"无效的输入"')
def step_impl(context):
    raise NotImplementedError(u'STEP: Then 错误信息应包含"无效的输入"')