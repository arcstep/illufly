import pytest
import asyncio
import zmq.asyncio
import logging
import tempfile
import shutil
import json

from illufly.rocksdb import IndexedRocksDB
from illufly.mq.service import ServiceRouter, ClientDealer
from illufly.community.models import TextChunk, TextFinal, ToolCallFinal, BlockType
from illufly.community.fake import ChatFake
from illufly.community.openai import ChatOpenAI
from illufly.community.base_tool import BaseTool
from illufly.agent import ChatAgent

logger = logging.getLogger(__name__)

@pytest.fixture
def db_path():
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path)

@pytest.fixture
def db(db_path):
    db = IndexedRocksDB(db_path)
    try:
        yield db
    finally:
        db.close()

@pytest.fixture()
def event_loop():
    """创建事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture()
def zmq_context():
    """创建共享的 ZMQ Context"""
    context = zmq.asyncio.Context.instance()  # 使用单例模式获取 Context
    yield context

@pytest.fixture()
def router_address():
    """返回路由器地址

    - inproc 套接字地址必须使用相同的 Context 创建的 Router、Dealer 和 Client
    - tcp 套接字地址可以跨 Context 使用
    """
    # return "tcp://localhost:5555"
    return "inproc://router_abc"

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

@pytest.fixture
async def chat_fake_service(router, router_address, zmq_context, db):
    """ChatFake 服务实例"""
    llm = ChatFake(
        response=["Hello", "World"],
        sleep=0.01,
    )
    agent = ChatAgent(llm=llm, db=db, router_address=router_address, context=zmq_context)
    await agent.start()
    yield agent
    await agent.stop()

@pytest.fixture
async def chat_openai_service(router, router_address, zmq_context, db, mock_tool):
    """ChatOpenAI 服务实例"""
    llm = ChatOpenAI(imitator="QWEN", model="qwen-turbo")
    # llm = ChatOpenAI(imitator="ZHIPU", model="glm-4-flash")
    # llm = ChatOpenAI(imitator="OPENAI", model="gpt-4o-mini")
    agent = ChatAgent(llm=llm, db=db, runnable_tools=[mock_tool], router_address=router_address, context=zmq_context, group="mychat")
    await agent.start()
    yield agent
    await agent.stop()

@pytest.fixture
def mock_tool():
    """模拟工具类"""
    class GetWeather(BaseTool):
        name = "get_weather"
        description = "获取天气信息"
        
        @classmethod
        async def call(cls, city: str):
            yield TextFinal(text=f"{city} 的天气是晴天")
    
    return GetWeather()

@pytest.mark.asyncio
async def test_chat_fake_basic(chat_fake_service, router_address, zmq_context):
    """测试基本聊天功能"""
    client = ClientDealer(router_address, context=zmq_context, timeout=5.0)
    thread_id = "test_thread_id"
    
    # 发送请求并收集响应
    responses = []
    async for chunk in client.stream("ChatFake.chat", messages="Test message", thread_id=thread_id):
        logger.info(f"chunk: {chunk}")
        if chunk.block_type == BlockType.TEXT_CHUNK:
            responses.append(chunk.content)
    logger.info(f"responses: {responses}")
    
    # 验证响应
    assert len(responses) > 0, "应该收到响应"
    assert "".join(responses) in ["Hello", "World"], "响应内容应该匹配预设"
    
    # 清理
    await client.close()

@pytest.mark.asyncio
async def test_chat_openai_basic(chat_openai_service, router_address, zmq_context):
    """测试基本聊天功能"""
    client = ClientDealer(router_address, context=zmq_context, timeout=5.0)
    thread_id = "test_thread_id"
    
    # 发送请求并收集响应
    responses = []
    async for chunk in client.stream("mychat.chat", messages="请重复一遍这句话：我很棒！", thread_id=thread_id):
        logger.info(f"chunk: {chunk}")
        if chunk.block_type == BlockType.TEXT_CHUNK:
            responses.append(chunk.content)
    logger.info(f"responses: {responses}")
    
    # 验证响应
    assert len(responses) > 0, "应该收到响应"
    assert "我很棒" in "".join(responses), "响应内容应该匹配预设"
    
    # 清理
    await client.close()

@pytest.mark.asyncio
async def test_runnable_tool_calls(chat_openai_service: ChatOpenAI, router_address, zmq_context):
    """测试完整的工具调用流程"""
    client = ClientDealer(router_address, context=zmq_context, timeout=5.0)
    thread_id = "test_thread_id"
    messages = "请帮我确认明天广州是否适合晒被子"
    
    final_text = ""
    async for chunk in client.stream("mychat.chat", messages, thread_id=thread_id):
        logger.info(f"[{chunk.block_type}] {chunk.text}")
        if chunk.block_type == BlockType.TEXT_FINAL:
            final_text = chunk.text
    
    # 验证最终回复包含处理结果
    assert "晴天" in final_text, "应正确处理工具返回结果"

@pytest.mark.asyncio
async def test_tool_calls(chat_openai_service: ChatOpenAI, router_address, zmq_context):
    """由客户端进行工具回调"""
    class GetWeather(BaseTool):
        name = "get_weather"
        description = "获取天气信息"
        
        @classmethod
        async def call(cls, city: str):
            yield TextFinal(text=f"{city} 的天气是暴雨")

    messages = [{
        "role": "user",
        "content": "请帮我看看明天广州的天气"
    }]
    
    client = ClientDealer(router_address, context=zmq_context, timeout=5.0)
    thread_id = "test_thread_id_with_tool"

    # 第一阶段：获取工具调用请求
    assistant_messages = []
    tool_calls = []
    async for chunk in client.stream("mychat.chat", messages=messages, thread_id=thread_id, tools=[GetWeather.to_openai()]):
        # logger.info(f"chunk: {chunk}")
        if chunk.block_type == BlockType.TOOL_CALL_FINAL:
            tool_calls.append(chunk)
        if chunk.block_type == BlockType.TEXT_CHUNK:
            # 收集assistant的文本响应（如果有）
            assistant_messages.append(chunk.content)

    assert len(tool_calls) > 0, "应该收到工具调用请求"
    
    # 必须将assistant的响应添加到消息历史
    if assistant_messages:
        messages.append({
            "role": "assistant",
            "content": "".join(assistant_messages)
        })
    if tool_calls:
        messages.append({
            "role": "assistant",
            "tool_calls": [{
                "id": tc.tool_call_id,
                "type": "function",
                "function": {
                    "name": tc.tool_name,
                    "arguments": tc.arguments
                }
            } for tc in tool_calls]
        })
    
    # 执行工具调用
    tool_responses = []
    for tc in tool_calls:
        async for resp in GetWeather.call(city=json.loads(tc.arguments)["city"]):
            if resp.block_type == BlockType.TEXT_FINAL:
                tool_responses.append({
                    "tool_call_id": tc.tool_call_id,
                    "content": resp.text
                })
    
    # 添加工具响应到消息历史（必须包含对应的tool_call_id）
    for resp in tool_responses:
        messages.append({
            "role": "tool",
            "tool_call_id": resp["tool_call_id"],
            "content": resp["content"]
        })
    
    # 第二阶段：处理工具结果
    final_text = ""
    async for chunk in client.stream("mychat.chat", messages, thread_id=thread_id, tools=[GetWeather.to_openai()]):
        if chunk.block_type == BlockType.TEXT_FINAL:
            final_text = chunk.content
    
    # 验证最终回复包含处理结果
    assert "暴雨" in final_text, "应正确处理工具返回结果"

@pytest.mark.asyncio
async def test_list_models(chat_openai_service: ChatOpenAI, router_address, zmq_context):
    """测试列出所有模型"""
    client = ClientDealer(router_address, context=zmq_context, timeout=5.0)
    
    models = []
    async for item in client.stream("mychat.models"):
        logger.info(f"model info: {item.__class__} / {item}")
        models = [m['id'] for m in item]
    logger.info(f"{models}")

    # 验证最终回复包含处理结果
    assert "qwen-plus" in models, "应正确列出所有模型"
