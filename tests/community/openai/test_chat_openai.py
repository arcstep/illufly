import pytest
import asyncio
import zmq.asyncio
import logging
from illufly.mq.service import ClientDealer, ServiceRouter
from illufly.mq.llm.chat_openai import ChatOpenAI

logger = logging.getLogger(__name__)

@pytest.fixture(autouse=True)
def setup_logging(caplog):
    """设置日志级别"""
    for handler in logging.getLogger().handlers:
        handler.setLevel(logging.DEBUG)
    caplog.set_level(logging.DEBUG)

@pytest.fixture()
def event_loop():
    """创建事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture()
def zmq_context():
    """创建共享的 ZMQ Context"""
    context = zmq.asyncio.Context.instance()
    yield context

@pytest.fixture()
def router_address():
    """返回路由器地址"""
    return "inproc://router_openai"

@pytest.fixture()
async def router(router_address, zmq_context):
    """创建并启动路由器"""
    router = ServiceRouter(
        router_address, 
        context=zmq_context
    )
    await router.start()
    await asyncio.sleep(0.1)
    yield router
    # 在停止前等待一小段时间，确保能处理所有关闭请求
    await asyncio.sleep(0.5)
    await router.stop()

@pytest.fixture()
async def chat_openai_service(router,router_address, zmq_context):
    """ChatOpenAI 服务实例"""
    service = ChatOpenAI(
        router_address=router_address,
        context=zmq_context,
    )
    await service.start()
    yield service
    await service.stop()

@pytest.mark.asyncio
async def test_chat_openai_basic(chat_openai_service, router_address, zmq_context):
    """测试基本聊天功能"""
    # 启动服务
    await chat_openai_service.start()
    
    # 创建客户端
    client = ClientDealer(router_address, context=zmq_context, timeout=2.0)
    
    # 发送请求并收集响应
    messages = [{"role": "user", "content": "请你重复我的话：你好"}]
    response = ""
    async for chunk in client.call_service("chat", messages):
        logger.info(f"Received chunk: {chunk}")
        if hasattr(chunk, "text"):
            response += chunk.text
    
    # 验证响应
    assert len(response) > 0, "应该收到响应"
    assert "你好" in response, "响应应该包含输入内容"
    
    # 清理
    await client.close()
    await chat_openai_service.stop()

@pytest.mark.asyncio
async def test_chat_openai_vision(chat_openai_service, router_address, zmq_context):
    """测试视觉模型功能"""
    await chat_openai_service.start()
    
    client = ClientDealer(router_address, context=zmq_context, timeout=2.0)
    
    # 发送包含图片的请求
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this image"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://example.com/image.jpg"
                    }
                }
            ]
        }
    ]
    
    responses = []
    async for chunk in client.call_service("chat", messages):
        if hasattr(chunk, "text"):
            responses.append(chunk.text)
    
    # 验证响应
    assert len(responses) > 0, "应该收到视觉模型的响应"
    
    await client.close()
    await chat_openai_service.stop()

@pytest.mark.asyncio
async def test_chat_openai_tool_calls(chat_openai_service, router_address, zmq_context):
    """测试工具调用功能"""
    await chat_openai_service.start()
    
    client = ClientDealer(router_address, context=zmq_context, timeout=2.0)
    
    # 发送包含工具调用的请求
    messages = [{"role": "user", "content": "What's the weather in Beijing?"}]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_current_weather",
                "description": "Get the current weather in a given location",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "The city and state, e.g. San Francisco, CA",
                        },
                        "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                    },
                    "required": ["location"],
                },
            }
        }
    ]
    
    tool_calls = []
    async for chunk in client.call_service("chat", messages, tools=tools):
        if hasattr(chunk, "name"):  # ToolCallChunk
            tool_calls.append(chunk)
    
    # 验证工具调用
    assert len(tool_calls) > 0, "应该收到工具调用响应"
    assert any(call.name == "get_current_weather" for call in tool_calls), "应该包含天气查询工具调用"
    
    await client.close()
    await chat_openai_service.stop() 