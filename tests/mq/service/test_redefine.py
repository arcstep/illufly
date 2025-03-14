import pytest
import asyncio
import zmq.asyncio
import logging
from illufly.mq.service import ServiceRouter, ServiceDealer, ClientDealer, service_method
from illufly.mq.models import StreamingBlock, BlockType

logger = logging.getLogger(__name__)

@pytest.fixture(autouse=True)
def setup_logging(caplog):
    """设置日志级别"""
    # 重置所有处理器的日志级别
    for handler in logging.getLogger().handlers:
        handler.setLevel(logging.DEBUG)
    # 设置 caplog 捕获级别
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
async def service(router, router_address, zmq_context, test_config):
    """创建并启动服务"""
    service = EchoService(
        router_address,
        context=zmq_context,
        heartbeat_interval=test_config['dealer_heartbeat']
    )
    await service.start()
    yield service
    # 确保在 router 关闭前完成服务关闭
    await service.stop()
    await asyncio.sleep(0.1)  # 给 router 一点时间处理关闭确认

@pytest.fixture
async def streaming_service(router, router_address, zmq_context, test_config):
    """创建并启动服务"""
    service = StreamingService(
        router_address,
        context=zmq_context,
        heartbeat_interval=test_config['dealer_heartbeat']
    )
    await service.start()
    yield service
    # 确保在 router 关闭前完成服务关闭
    await service.stop()
    await asyncio.sleep(0.1)  # 给 router 一点时间处理关闭确认

@pytest.fixture
async def client(router, service, router_address, zmq_context):
    """创建客户端"""
    # 确保服务已经注册
    assert service._running, "Service not running"
    
    client = ClientDealer(router_address, context=zmq_context, timeout=2.0)
    try:
        yield client
    finally:
        await client.close()

@pytest.fixture
async def streaming_client(router, streaming_service, router_address, zmq_context):
    """创建客户端"""
    # 确保服务已经注册
    assert streaming_service._running, "Service not running"
    
    client = ClientDealer(router_address, context=zmq_context, timeout=2.0)
    try:
        yield client
    finally:
        await client.close()

class BasicEchoService(ServiceDealer):
    """示例服务实现"""
    def __init__(self, router_address: str, context = None, heartbeat_interval: float = 0.5):
        super().__init__(
            router_address=router_address,
            context=context
        )
        self._heartbeat_interval = heartbeat_interval

    @service_method
    async def echo(self, message: str) -> str:
        """简单回显服务"""
        await asyncio.sleep(0.1)
        logger.info(f"EchoService {self._service_id} echo: {message}")
        return message

class EchoService(BasicEchoService):
    """示例服务实现"""
    @service_method(
        name="add",
        description="Add two numbers",
        params={
            "a": "first number",
            "b": "second number"
        }
    )
    async def add_numbers(self, a: int, b: int) -> int:
        """带参数说明的加法服务"""
        await asyncio.sleep(0.01)
        return a + b

class StreamingService(BasicEchoService):
    """示例服务实现"""
    @service_method(name="stream")
    async def stream_numbers(self, start: int, end: int):
        """流式返回数字序列"""
        for i in range(start, end):
            yield i
            await asyncio.sleep(0.1)  # 模拟处理延迟

@pytest.mark.asyncio
async def test_simple_echo(client):
    """测试简单的回显服务"""
    message = "Hello, World!"
    async for response in client.stream("EchoService.echo", message):
        assert response == message
        break

@pytest.mark.asyncio
async def test_service_discovery(client):
    """测试服务发现"""
    available_methods = await client.discover_services()
    
    # 验证可用方法
    assert "EchoService.echo" in available_methods
    assert "EchoService.add" in available_methods
    
    # 验证方法描述信息
    add_info = available_methods["EchoService.add"]
    logger.info(f"add_info: {add_info}")
    assert add_info["description"] == "Add two numbers"
    assert "a" in add_info["params"]
    assert "b" in add_info["params"]

@pytest.mark.asyncio
async def test_streaming_response(streaming_client):
    """测试流式响应"""
    expected = list(range(0, 5))
    received = []
    
    async for response in streaming_client.stream("StreamingService.stream", 0, 5):
        received.append(response)
            
    assert received == expected
