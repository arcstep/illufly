import pytest
import asyncio
import zmq.asyncio
import logging
from illufly.mq.service import ServiceRouter, ServiceDealer, ClientDealer
from illufly.mq.models import StreamingBlock, BlockType

# 确保在导入后就配置好日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s - %(name)s - %(message)s'
)

logger = logging.getLogger(__name__)

@pytest.fixture(autouse=True)
def setup_logging(caplog):
    """设置日志级别"""
    # 重置所有处理器的日志级别
    for handler in logging.getLogger().handlers:
        handler.setLevel(logging.DEBUG)
    # 设置 caplog 捕获级别
    caplog.set_level(logging.DEBUG)

@pytest.fixture(scope="module")
def event_loop():
    """创建事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="module")
def zmq_context():
    """创建共享的 ZMQ Context"""
    context = zmq.asyncio.Context.instance()  # 使用单例模式获取 Context
    yield context

@pytest.fixture(scope="module")
def router_address():
    # return "tcp://localhost:5555"
    return "inproc://router_abc"

@pytest.fixture(scope="module")
async def router(router_address, zmq_context):
    """创建并启动路由器"""
    router = ServiceRouter(router_address, context=zmq_context)
    await router.start()
    # 确保 Router 完全启动并绑定
    await asyncio.sleep(0.1)  # 给足够的时间让 Router 绑定地址
    
    try:
        yield router
    finally:
        await router.stop()

@pytest.fixture(scope="module")
async def service(router, router_address, zmq_context):
    """创建并启动服务"""
    # 确保 Router 已经完全启动
    assert router._running, "Router not running"
    assert router._socket.closed == False, "Router socket closed"
    
    service = EchoService(router_address, context=zmq_context)
    await service.start()
    try:
        yield service
    finally:
        await service.stop()

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

class EchoService(ServiceDealer):
    """示例服务实现"""
    def __init__(self, router_address: str, context = None):
        super().__init__(
            router_address=router_address,
            service_id="echo_service",
            context=context
        )

    @ServiceDealer.service_method()  # 使用默认方法名
    async def echo(self, message: str) -> str:
        """简单回显服务"""
        return message

    @ServiceDealer.service_method(name="stream")
    async def stream_numbers(self, start: int, end: int):
        """流式返回数字序列"""
        for i in range(start, end):
            yield str(i)
            await asyncio.sleep(0.1)  # 模拟处理延迟

    @ServiceDealer.service_method(
        name="add",
        description="Add two numbers",
        params={
            "a": "first number",
            "b": "second number"
        }
    )
    async def add_numbers(self, a: int, b: int) -> int:
        """带参数说明的加法服务"""
        return a + b

@pytest.mark.asyncio
async def test_simple_echo(router, service, client):
    """测试简单的回显服务"""
    message = "Hello, World!"
    async for response in client.call_service("echo", message):
        assert response == message
        break

@pytest.mark.asyncio
async def test_add_numbers(router, service, client):
    """测试带参数的加法服务"""
    async for response in client.call_service("add", 5, 3):
        assert response == 8
        break

@pytest.mark.asyncio
async def test_streaming_response(router, service, client):
    """测试流式响应"""
    expected = [str(i) for i in range(0, 5)]
    received = []
    
    async for response in client.call_service("stream", 0, 5):
        received.append(response)
            
    assert received == expected

@pytest.mark.asyncio
async def test_service_discovery(router, service, client):
    """测试服务发现"""
    services = await client.discover_services()
    assert "echo_service" in services
    service_info = services["echo_service"]
    
    # 验证服务方法信息
    assert "echo" in service_info
    assert "add" in service_info
    assert "stream" in service_info
    
    # 验证方法描述信息
    add_info = service_info["add"]
    logger.info(f"add_info: {service_info}")
    assert add_info["description"] == "Add two numbers"
    assert "a" in add_info["params"]
    assert "b" in add_info["params"]

@pytest.mark.asyncio
async def test_concurrent_requests(router, service, client):
    """测试并发请求"""
    async def make_request(a: int, b: int):
        async for response in client.call_service("add", a, b):
            assert response == a + b
            break

    # 创建多个并发请求
    requests = [
        make_request(i, i+1)
        for i in range(10)
    ]
    await asyncio.gather(*requests)

@pytest.mark.asyncio
async def test_connection_reuse(router, service, client):
    """测试连接重用"""
    # 第一次调用
    async for response in client.call_service("echo", "test1"):
        assert response == "test1"
        break
        
    # 第二次调用（应该重用连接）
    async for response in client.call_service("echo", "test2"):
        assert response == "test2"
        break

@pytest.mark.asyncio
async def test_auto_reconnect(router, service, client):
    """测试自动重连"""
    # 第一次调用
    async for response in client.call_service("echo", "test1"):
        assert response == "test1"
        break
    
    # 模拟连接断开
    await client.close()
    
    # 第二次调用（应该自动重连）
    async for response in client.call_service("echo", "test2"):
        assert response == "test2"
        break

@pytest.mark.asyncio
async def test_timeout(router, service, client):
    """测试超时处理"""
    with pytest.raises(TimeoutError):
        async for _ in client.call_service("echo", "test", timeout=0.001):
            await asyncio.sleep(0.1)  # 强制超时

@pytest.mark.asyncio
async def test_service_not_found(router, client):
    """测试请求不存在的服务"""
    with pytest.raises(RuntimeError) as exc_info:
        async for _ in client.call_service("non_existent", "test"):
            pass
    assert "not found" in str(exc_info.value)