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
    """返回路由器地址

    - inproc 套接字地址必须使用相同的 Context 创建的 Router、Dealer 和 Client
    - tcp 套接字地址可以跨 Context 使用
    """
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
    service = EchoService(router_address, context=zmq_context)
    await service.start()
    yield service
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

@pytest.fixture
async def second_service(router, router_address, zmq_context):
    """创建第二个服务实例"""
    service = EchoService(router_address, context=zmq_context)
    await service.start()
    yield service
    await service.stop()

class EchoService(ServiceDealer):
    """示例服务实现"""
    def __init__(self, router_address: str, context = None):
        super().__init__(
            router_address=router_address,
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

@pytest.mark.asyncio
async def test_load_balancing(router, service, second_service, client):
    """测试负载均衡功能"""
    # 记录每个服务处理的请求
    responses = []
    
    # 发送多个请求
    for i in range(10):
        async for response in client.call_service("echo", f"test_{i}"):
            responses.append(response)
            break
    
    # 检查服务发现，应该能看到两个服务
    services = await client.discover_services()
    assert len(services) == 2, "应该有两个服务注册"
    
    # 检查响应是否正确
    assert len(responses) == 10, "应该收到所有请求的响应"
    assert all(resp == f"test_{i}" for i, resp in enumerate(responses)), "响应内容应该正确"

@pytest.mark.asyncio
async def test_service_failover(router, service, second_service, client):
    """测试服务故障转移"""
    # 首先确认两个服务都在工作
    async for response in client.call_service("echo", "test1"):
        assert response == "test1"
        break
    
    # 停止第一个服务
    await service.stop()
    await asyncio.sleep(0.1)  # 给路由器一点时间处理服务下线
    
    # 确认仍然可以通过第二个服务处理请求
    async for response in client.call_service("echo", "test2"):
        assert response == "test2"
        break
    
    # 检查服务发现，应该只剩一个服务
    services = await client.discover_services()
    assert len(services) == 1, "应该只剩一个服务"

@pytest.mark.asyncio
async def test_concurrent_load_balancing(router, service, second_service, client):
    """测试并发负载均衡"""
    async def make_request(i: int):
        async for response in client.call_service("echo", f"test_{i}"):
            assert response == f"test_{i}"
            break
    
    # 创建多个并发请求
    tasks = [
        make_request(i)
        for i in range(20)
    ]
    await asyncio.gather(*tasks)

@pytest.mark.asyncio
async def test_service_registration_order(router, router_address, zmq_context):
    """测试服务注册顺序不影响负载均衡"""
    # 创建多个服务实例
    services = []
    try:
        # 依次启动3个服务
        for i in range(3):
            service = EchoService(router_address, context=zmq_context)
            await service.start()
            services.append(service)
            await asyncio.sleep(0.1)  # 给一点时间注册
        
        # 创建客户端
        client = ClientDealer(router_address, context=zmq_context)
        
        # 发送请求并检查负载均衡
        responses = []
        for i in range(9):  # 发送9个请求，应该每个服务处理3个
            async for response in client.call_service("echo", f"test_{i}"):
                responses.append(response)
                break
        
        # 验证所有请求都得到处理
        assert len(responses) == 9, "应该收到所有请求的响应"
        assert all(resp == f"test_{i}" for i, resp in enumerate(responses)), "响应内容应该正确"
        
        # 检查服务发现
        services_info = await client.discover_services()
        assert len(services_info) == 3, "应该有3个服务注册"
        
    finally:
        # 清理服务实例
        for service in services:
            await service.stop()
        await client.close()

@pytest.mark.asyncio
async def test_service_health_check(router, service, second_service, client):
    """测试服务健康检查"""
    # 首先确认两个服务都在工作
    services = await client.discover_services()
    assert len(services) == 2, "应该有两个服务注册"
    
    # 模拟服务故障（强制关闭socket）
    service._socket.close()
    
    # 等待健康检查发现故障（超过心跳超时时间）
    await asyncio.sleep(11)  # 健康检查超时是10秒
    
    # 检查服务发现，应该只剩一个服务
    services = await client.discover_services()
    assert len(services) == 1, "应该只剩一个服务"
    
    # 确认剩余服务仍然可用
    async for response in client.call_service("echo", "test"):
        assert response == "test"
        break