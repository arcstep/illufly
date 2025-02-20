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
        handler.setLevel(logging.INFO)
    # 设置 caplog 捕获级别
    caplog.set_level(logging.INFO)

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
    def __init__(self, router_address: str, context = None, heartbeat_interval: float = 0.5):
        super().__init__(
            router_address=router_address,
            context=context
        )
        self._heartbeat_interval = heartbeat_interval

    @service_method # 使用默认方法名
    async def echo(self, message: str) -> str:
        """简单回显服务"""
        await asyncio.sleep(0.1)
        logger.info(f"EchoService {self._service_id} echo: {message}")
        return message

    @service_method(name="stream")
    async def stream_numbers(self, start: int, end: int):
        """流式返回数字序列"""
        for i in range(start, end):
            yield i
            await asyncio.sleep(0.1)  # 模拟处理延迟

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

@pytest.mark.asyncio
async def test_simple_echo(router, service, client):
    """测试简单的回显服务"""
    message = "Hello, World!"
    async for response in client.call_service("echoservice.echo", message):
        assert response == message
        break
    await service.stop()

@pytest.mark.asyncio
async def test_add_numbers(router, service, client):
    """测试带参数的加法服务"""
    async for response in client.call_service("echoservice.add", 5, 3):
        assert response == 8
        break

@pytest.mark.asyncio
async def test_streaming_response(router, service, client):
    """测试流式响应"""
    expected = list(range(0, 5))
    received = []
    
    async for response in client.call_service("echoservice.stream", 0, 5):
        received.append(response)
            
    assert received == expected

@pytest.mark.asyncio
async def test_service_discovery(router, service, client):
    """测试服务发现"""
    available_methods = await client.discover_services()
    
    # 验证可用方法
    assert "echoservice.echo" in available_methods
    assert "echoservice.add" in available_methods
    assert "echoservice.stream" in available_methods
    
    # 验证方法描述信息
    add_info = available_methods["echoservice.add"]
    logger.info(f"add_info: {add_info}")
    assert add_info["description"] == "Add two numbers"
    assert "a" in add_info["params"]
    assert "b" in add_info["params"]

@pytest.mark.asyncio
async def test_concurrent_requests(router, service, client):
    """测试并发请求"""
    async def make_request(a: int, b: int):
        async for response in client.call_service("echoservice.add", a, b):
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
    async for response in client.call_service("echoservice.echo", "test1"):
        assert response == "test1"
        break
        
    # 第二次调用（应该重用连接）
    async for response in client.call_service("echoservice.echo", "test2"):
        assert response == "test2"
        break

@pytest.mark.asyncio
async def test_auto_reconnect(router, service, client):
    """测试自动重连"""
    # 第一次调用
    async for response in client.call_service("echoservice.echo", "test1"):
        assert response == "test1"
        break
    
    # 模拟连接断开
    await client.close()
    await asyncio.sleep(0.1)
    
    # 第二次调用（应该自动重连）
    async for response in client.call_service("echoservice.echo", "test2"):
        assert response == "test2"
        break

@pytest.mark.asyncio
async def test_timeout(router, service, client):
    """测试超时处理"""
    with pytest.raises(TimeoutError):
        async for _ in client.call_service("echoservice.echo", "test", timeout=0.001):
            await asyncio.sleep(0.1)  # 强制超时

@pytest.mark.asyncio
async def test_service_not_found(router, client):
    """测试请求不存在的服务"""
    with pytest.raises(RuntimeError) as exc_info:
        async for _ in client.call_service("echoservice.non_existent", "test"):
            pass
    assert "not found" in str(exc_info.value)

@pytest.mark.asyncio
async def test_load_balancing(router, service, second_service, router_address, zmq_context):
    """测试负载均衡功能"""
    # 记录每个服务处理的请求
    responses = []
    
    # 发送多个请求
    clients = []
    tasks = []
    for i in range(10):
        client = ClientDealer(router_address, context=zmq_context, timeout=2.0)
        clients.append(client)
        # 将异步生成器转换为协程
        tasks.append(client.call_service("echoservice.echo", f"test_{i}").__anext__())
    
    responses = await asyncio.gather(*tasks)
    
    # 检查服务发现，应该能看到两个服务
    clusters = await clients[0].discover_clusters()
    assert len(clusters.keys()) == 2, "应该有两个服务注册"
    
    # 检查响应是否正确
    assert len(responses) == 10, "应该收到所有请求的响应"
    assert all(resp == f"test_{i}" for i, resp in enumerate(responses)), "响应内容应该正确"

    for client in clients:
        await client.close()

@pytest.mark.asyncio
async def test_service_failover(router, service, second_service, client):
    """测试服务故障转移"""
    # 首先确认两个服务都在工作
    all_clusters = await client.discover_clusters()
    logger.info(f"all_clusters: {all_clusters}")
    clusters = {k: v for k, v in all_clusters.items() if v['state'] == 'active'}
    assert len(clusters.keys()) == 2

    async for response in client.call_service("echoservice.echo", "test1"):
        assert response == "test1"
        break
    
    # 停止第一个服务
    await service.stop()
    await asyncio.sleep(0.1)  # 给路由器一点时间处理服务下线
    
    # 确认仍然可以通过第二个服务处理请求
    async for response in client.call_service("echoservice.echo", "test2"):
        assert response == "test2"
        break
    
    # 检查服务发现，应该只剩一个服务
    all_clusters = await client.discover_clusters()
    logger.info(f"all_clusters: {all_clusters}")
    clusters = {k: v for k, v in all_clusters.items() if v['state'] == 'active'}
    assert len(clusters.keys()) == 1, "应该只剩一个服务"
