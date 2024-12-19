from behave import given, when, then

@given('FastAPI 已经准备好')
def step_impl(context):
    assert context.client is not None
    print("FastAPI 已经准备好")

@given('清理测试数据')
def step_impl(context):
    print("清理测试数据")
