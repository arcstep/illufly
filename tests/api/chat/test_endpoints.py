import pytest
import logging
import zmq.asyncio
import tempfile
import shutil
import asyncio

from fastapi.testclient import TestClient
from fastapi import FastAPI, Request, Response
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from fastapi import HTTPException, status

from illufly.api.auth.tokens import TokensManager, TokenClaims, TokenType
from illufly.thread.thread_manager import ThreadManagerDealer
from illufly.mq.service import ClientDealer, ServiceRouter
from illufly.rocksdb import IndexedRocksDB

from illufly.api.chat.endpoints import create_chat_endpoints
from illufly.api.models import Result

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 模拟数据库

mock_tokens_manager = MagicMock()
mock_users_manager = MagicMock()

@pytest.fixture
def zmq_context():
    """创建测试客户端"""
    yield zmq.asyncio.Context()

@pytest.fixture
def router_address():
    """创建测试客户端"""
    return "tcp://localhost:5555"

@pytest.fixture
async def zmq_client(zmq_context, router_address):
    """创建测试客户端"""
    client = ClientDealer(router_address, context=zmq_context, timeout=2.0)
    yield client
    await client.close()

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
async def thread_manager(router, router_address, zmq_context, db):
    """创建并启动线程管理器"""
    thread_manager = ThreadManagerDealer(db=db, router_address=router_address, context=zmq_context)
    await thread_manager.start()
    yield thread_manager
    await thread_manager.stop()

@pytest.fixture
def client(zmq_client, thread_manager):
    """创建测试客户端"""
    # 模拟管理器
    global mock_tokens_manager
    mock_tokens_manager = MagicMock()

    # 获取路由处理函数
    app = FastAPI()
    route_handlers = create_chat_endpoints(
        app=app,
        zmq_client=zmq_client,
        tokens_manager=mock_tokens_manager,
        prefix="/api"
    )

    # 注册路由
    for _, (method, path, handler) in route_handlers.items():
        getattr(app, method)(path)(handler)

    return TestClient(app)

@pytest.fixture
def mock_user_dict():
    """模拟用户信息"""
    return {
        "user_id": "123",
        "username": "testuser",
        "email": "testuser@example.com",
        "roles": ["user"]
    }

@pytest.fixture
def mock_token_dict(mock_user_dict):
    """模拟令牌信息"""
    return {
        "token_type": TokenType.ACCESS,
        "user_id": "123",
        "username": "testuser",
        "roles": ["user"],
        "device_id": "device123"
    }

@pytest.mark.asyncio
async def test_all_threads_with_zmq(thread_manager, zmq_client):
    threads = await zmq_client.invoke("ThreadManagerDealer.all_threads", user_id="123", timeout=1.0)
    logger.info(f"【直接访问】所有对话历史: {threads[0]}")
    assert len(threads[0]) == 0

    threads = []
    async for chunk in zmq_client.stream("ThreadManagerDealer.all_threads", user_id="123", timeout=1.0):
        threads.append(chunk)
    logger.info(f"【直接访问】所有对话历史: {threads[0]}")
    assert len(threads[0]) == 0

@pytest.mark.asyncio
async def test_all_threads(thread_manager, mock_token_dict, zmq_client):
    global mock_tokens_manager
    mock_tokens_manager = MagicMock()

    # 获取路由处理函数
    app = FastAPI()
    route_handlers = create_chat_endpoints(
        app=app,
        client=zmq_client,
        tokens_manager=mock_tokens_manager,
        prefix="/api"
    )

    # 注册路由
    for _, (method, path, handler) in route_handlers.items():
        getattr(app, method)(path)(handler)
    
    fastapi_client = TestClient(app)

    # 调用获取用户信息接口
    mock_tokens_manager.verify_access_token.return_value = Result.ok(data=mock_token_dict)
    fastapi_client.cookies.set("access_token", "valid_token")
    response = fastapi_client.get("/api/chat/threads")
    logger.info(f"【FastAPI】所有对话历史: {response.json()}")

    # 验证结果
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert len(response_data) == 0