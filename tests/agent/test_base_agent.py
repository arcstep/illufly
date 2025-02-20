import pytest
import asyncio
import zmq.asyncio
import logging
import tempfile
import shutil

from illufly.mq.service import ServiceRouter, ClientDealer
from illufly.mq.models import TextChunk
from illufly.agent.chat_agent import BaseAgent
from illufly.community.fake import ChatFake
from illufly.rocksdb import IndexedRocksDB

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
        'heartbeat_timeout': 2.0,    # Router 心跳超时时间
        'dealer_heartbeat': 0.25,    # Dealer 心跳发送间隔
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

@pytest.mark.asyncio
async def test_chat_fake_basic(chat_fake_service, router_address, zmq_context):
    """测试基本聊天功能"""
    client = ClientDealer(router_address, context=zmq_context, timeout=1.0)
    thread_id = "test_thread_id"
    
    # 发送请求并收集响应
    responses = []
    async for chunk in client.call_service("chat", messages="Test message", thread_id=thread_id):
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
    async for chunk in client.call_service("chat", "Test 1"):
        if isinstance(chunk, TextChunk):
            responses1.append(chunk.content)
    
    # 第二次调用
    responses2 = []
    async for chunk in client.call_service("chat", "Test 2"):
        if isinstance(chunk, TextChunk):
            responses2.append(chunk.content)
    
    # 验证响应轮换
    assert "".join(responses1) != "".join(responses2), "两次调用应该返回不同的预设响应"
    
    await client.close()
