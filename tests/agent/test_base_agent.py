import pytest
import asyncio
import zmq.asyncio
import logging
import tempfile
import shutil

from illufly.rocksdb import IndexedRocksDB
from illufly.mq.service import ServiceRouter, ClientDealer
from illufly.community.models import TextChunk, TextFinal
from illufly.community.fake import ChatFake
from illufly.community.openai import ChatOpenAI
from illufly.community.base_tool import BaseTool
from illufly.agent.chat_agent import BaseAgent

logger = logging.getLogger(__name__)

@pytest.fixture
def db_path():
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path)

@pytest.fixture
def db(db_path):
    db = IndexedRocksDB(db_path, logger=logger)
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
def test_config():
    """测试配置"""
    return {
        'heartbeat_interval': 0.5,   # Router 心跳检查间隔
        'heartbeat_timeout': 5.0,    # Router 心跳超时时间
        'dealer_heartbeat': 1.0,    # Dealer 心跳发送间隔
    }

@pytest.fixture()
async def router(router_address, zmq_context, test_config):
    """创建并启动路由器"""
    router = ServiceRouter(
        router_address, 
        context=zmq_context,
        heartbeat_interval=test_config['heartbeat_interval'],
        heartbeat_timeout=test_config['heartbeat_timeout']
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
    agent = BaseAgent(llm=llm, db=db, router_address=router_address, context=zmq_context)
    await agent.start()
    yield agent
    await agent.stop()

@pytest.fixture
async def chat_openai_service(router, router_address, zmq_context, db, mock_tool):
    """ChatOpenAI 服务实例"""
    llm = ChatOpenAI(imitator="ZHIPU", model="glm-4-flash")
    # llm = ChatOpenAI(imitator="OPENAI", model="gpt-4o-mini")
    agent = BaseAgent(llm=llm, db=db, tools=[mock_tool], router_address=router_address, context=zmq_context, group="mychat")
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
    client = ClientDealer(router_address, context=zmq_context, timeout=1.0)
    thread_id = "test_thread_id"
    
    # 发送请求并收集响应
    responses = []
    async for chunk in client.call_service("chatfake.chat", messages="Test message", thread_id=thread_id):
        logger.info(f"chunk: {chunk}")
        if isinstance(chunk, TextChunk):
            responses.append(chunk.content)
    logger.info(f"responses: {responses}")
    
    # 验证响应
    assert len(responses) > 0, "应该收到响应"
    assert "".join(responses) in ["Hello", "World"], "响应内容应该匹配预设"
    
    # 清理
    await client.close()

@pytest.mark.asyncio
async def test_chat_fake_multiple_responses(chat_fake_service, router_address, zmq_context):
    """测试多个响应轮换"""    
    client = ClientDealer(router_address, context=zmq_context, timeout=1.0)
    
    # 第一次调用
    responses1 = []
    async for chunk in client.call_service("chatfake.chat", "Test 1"):
        if isinstance(chunk, TextChunk):
            responses1.append(chunk.content)
    
    # 第二次调用
    responses2 = []
    async for chunk in client.call_service("chatfake.chat", "Test 2"):
        if isinstance(chunk, TextChunk):
            responses2.append(chunk.content)
    
    # 验证响应轮换
    assert "".join(responses1) != "".join(responses2), "两次调用应该返回不同的预设响应"
    
    await client.close()

@pytest.mark.asyncio
async def test_chat_openai_basic(chat_openai_service, router_address, zmq_context):
    """测试基本聊天功能"""
    client = ClientDealer(router_address, context=zmq_context, timeout=1.0)
    thread_id = "test_thread_id"
    
    # 发送请求并收集响应
    responses = []
    async for chunk in client.call_service("mychat.chat", messages="请重复一遍这句话：我很棒！", thread_id=thread_id):
        logger.info(f"chunk: {chunk}")
        if isinstance(chunk, TextChunk):
            responses.append(chunk.content)
    logger.info(f"responses: {responses}")
    
    # 验证响应
    assert len(responses) > 0, "应该收到响应"
    assert "我很棒" in "".join(responses), "响应内容应该匹配预设"
    
    # 清理
    await client.close()

@pytest.mark.asyncio
async def test_tool_calls(chat_openai_service: ChatOpenAI, router_address, zmq_context):
    """测试完整的工具调用流程"""
    client = ClientDealer(router_address, context=zmq_context, timeout=1.0)
    thread_id = "test_thread_id"
    messages = "请帮我确认明天广州是否适合晒被子"
    
    final_text = ""
    async for chunk in client.call_service("mychat.chat", messages, thread_id=thread_id):
        logger.info(f"[{chunk.block_type}] {chunk.content}")
        if isinstance(chunk, TextFinal):
            final_text = chunk.content
    
    # 验证最终回复包含处理结果
    assert "晴天" in final_text, "应正确处理工具返回结果"
