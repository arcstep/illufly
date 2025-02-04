import pytest
import asyncio
import zmq.asyncio
import logging
from illufly.mq.service import ServiceRouter, ServiceDealer, ClientDealer
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
def test_config():
    """测试配置"""
    return {
        'heartbeat_interval': 0.5,   # Router 心跳检查间隔
        'heartbeat_timeout': 2.0,    # Router 心跳超时时间
        'dealer_heartbeat': 0.25,    # Dealer 心跳发送间隔
    }

@pytest.fixture(scope="module")
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

    @ServiceDealer.service_method()  # 使用默认方法名
    async def echo(self, message: str) -> str:
        """简单回显服务"""
        logger.info(f"EchoService {self._service_id} echo: {message}")
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
    await service.stop()

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
    available_methods = await client.discover_services()
    
    # 验证可用方法
    assert "echo" in available_methods
    assert "add" in available_methods
    assert "stream" in available_methods
    
    # 验证方法描述信息
    add_info = available_methods["add"]
    logger.info(f"add_info: {add_info}")
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
    await asyncio.sleep(0.1)
    
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

@pytest.mark.asyncio
async def test_service_overload_and_resume(router, service, client):
    """测试服务满载和恢复"""
    # 创建足够多的并发请求使服务接近满载
    async def slow_request(i: int):
        async for response in client.call_service("echo", f"test_{i}"):
            await asyncio.sleep(0.1)  # 模拟慢处理
            assert response == f"test_{i}"
            break

    # 发送大量并发请求（默认满载阈值是80%，即80个请求）
    tasks = [slow_request(i) for i in range(85)]
    
    # 等待一些请求完成
    await asyncio.sleep(0.5)
    
    # 此时服务应该报告满载
    services = await client.discover_services()
    service_info = next(iter(services.values()))
    assert service_info['state'] == 'overload'
    
    # 等待请求完成，服务应该自动恢复
    await asyncio.gather(*tasks)
    await asyncio.sleep(0.5)  # 给服务一点时间恢复
    
    # 验证服务已恢复
    services = await client.discover_services()
    service_info = next(iter(services.values()))
    assert service_info['state'] == 'active'
    
    # 确认服务恢复后可以正常处理请求
    async for response in client.call_service("echo", "test_after_resume"):
        assert response == "test_after_resume"
        break

@pytest.mark.asyncio
async def test_service_graceful_shutdown(router, service, second_service, client):
    """测试服务优雅下线"""
    # 确认初始有两个服务
    services = await client.discover_services()
    assert len(services) == 2
    
    # 优雅关闭第一个服务
    await service.stop()
    await asyncio.sleep(0.1)
    
    # 验证服务发现结果
    services = await client.discover_services()
    assert len(services) == 1
    
    # 确认剩余服务可用
    async for response in client.call_service("echo", "test"):
        assert response == "test"
        break

@pytest.mark.asyncio
async def test_service_failure_detection(router, service, second_service, client):
    """测试服务故障检测"""
    # 确认初始有两个服务
    services = await client.discover_services()
    assert len(services) == 2
    
    # 模拟服务崩溃（强制关闭socket）
    service._socket.close()
    
    # 等待健康检查发现故障
    await asyncio.sleep(31)  # 默认心跳超时是30秒
    
    # 验证故障服务被标记为不可用
    services = await client.discover_services()
    assert len(services) == 1
    
    # 确认剩余服务可用
    async for response in client.call_service("echo", "test"):
        assert response == "test"
        break

@pytest.mark.asyncio
async def test_service_recovery(router, router_address, zmq_context):
    """测试服务恢复"""
    # 创建并启动第一个服务
    service1 = EchoService(router_address, context=zmq_context)
    await service1.start()
    
    # 创建客户端
    client = ClientDealer(router_address, context=zmq_context)
    
    # 确认服务可用
    async for response in client.call_service("echo", "test1"):
        assert response == "test1"
        break
    
    # 模拟服务崩溃
    service1._socket.close()
    await asyncio.sleep(31)  # 等待健康检查发现故障
    
    # 重启服务
    await service1.start()
    await asyncio.sleep(0.1)  # 给服务一点时间注册
    
    # 确认服务恢复后可用
    async for response in client.call_service("echo", "test2"):
        assert response == "test2"
        break
    
    # 清理
    await service1.stop()
    await client.close()

@pytest.mark.asyncio
async def test_load_balancing_with_overload(router, router_address, zmq_context):
    """测试带有满载的负载均衡"""
    # 创建两个服务实例
    service1 = EchoService(router_address, context=zmq_context, max_concurrent=10)
    service2 = EchoService(router_address, context=zmq_context, max_concurrent=10)
    await service1.start()
    await service2.start()
    
    client = ClientDealer(router_address, context=zmq_context)
    
    try:
        # 创建慢请求使第一个服务接近满载
        async def slow_request(i: int):
            async for response in client.call_service("echo", f"test_{i}"):
                await asyncio.sleep(0.1)
                assert response == f"test_{i}"
                break
        
        # 发送足够多的请求使一个服务满载
        overload_tasks = [slow_request(i) for i in range(9)]  # 80% * 10 = 8
        await asyncio.sleep(0.2)  # 等待请求开始处理
        
        # 发送新请求，应该被路由到未满载的服务
        async for response in client.call_service("echo", "test_new"):
            assert response == "test_new"
            break
        
        # 等待所有请求完成
        await asyncio.gather(*overload_tasks)
        
    finally:
        # 清理
        await service1.stop()
        await service2.stop()
        await client.close()

@pytest.mark.asyncio
async def test_custom_overload_strategy(router, router_address, zmq_context):
    """测试自定义满载策略"""
    class CustomService(EchoService):
        def check_overload(self) -> bool:
            # 自定义策略：50%负载时报告满载
            return self._current_load >= self._max_concurrent * 0.5
        
        def check_can_resume(self) -> bool:
            # 自定义策略：30%负载时恢复
            return self._current_load <= self._max_concurrent * 0.3
    
    service = CustomService(router_address, context=zmq_context, max_concurrent=10)
    await service.start()
    client = ClientDealer(router_address, context=zmq_context)
    
    try:
        # 创建足够的请求使服务满载（按新策略）
        async def slow_request(i: int):
            async for response in client.call_service("echo", f"test_{i}"):
                await asyncio.sleep(0.1)
                assert response == f"test_{i}"
                break
        
        # 发送6个请求（超过50%阈值）
        tasks = [slow_request(i) for i in range(6)]
        await asyncio.sleep(0.2)
        
        # 验证服务已标记为满载
        services = await client.discover_services()
        service_info = next(iter(services.values()))
        assert service_info['state'] == 'overload'
        
        # 等待请求完成，负载降低到恢复阈值以下
        await asyncio.gather(*tasks)
        await asyncio.sleep(0.5)
        
        # 验证服务已恢复
        services = await client.discover_services()
        service_info = next(iter(services.values()))
        assert service_info['state'] == 'active'
        
    finally:
        await service.stop()
        await client.close()

@pytest.mark.asyncio
async def test_service_lifecycle(router, router_address, zmq_context, test_config):
    """测试服务生命周期：注册、故障检测、故障转移、恢复"""
    # 创建两个服务实例
    service1 = EchoService(
        router_address, 
        context=zmq_context,
        heartbeat_interval=test_config['dealer_heartbeat']
    )
    service2 = EchoService(
        router_address, 
        context=zmq_context,
        heartbeat_interval=test_config['dealer_heartbeat']
    )
    
    client = ClientDealer(router_address, context=zmq_context)
    
    try:
        # 1. 启动服务并验证注册
        await service1.start()
        await service2.start()
        await asyncio.sleep(0.1)
        
        services = await client.discover_services()
        assert len(services) == 2, "应该有两个服务注册"
        
        # 2. 测试基本功能
        async for response in client.call_service("echo", "test"):
            assert response == "test"
            break
        
        # 3. 模拟服务故障和故障转移
        service1._socket.close()
        await asyncio.sleep(test_config['heartbeat_timeout'] + 0.2)  # 等待故障检测
        
        # 验证故障转移
        services = await client.discover_services()
        assert len(services) == 1, "应该只剩一个服务"
        
        # 确认剩余服务可用
        async for response in client.call_service("echo", "failover"):
            assert response == "failover"
            break
        
        # 4. 测试服务恢复
        await service1.start()
        await asyncio.sleep(0.1)
        
        services = await client.discover_services()
        assert len(services) == 2, "服务应该已恢复"
        
        # 5. 测试优雅下线
        await service1.stop()
        await asyncio.sleep(0.1)
        
        services = await client.discover_services()
        assert len(services) == 1, "应该正确处理服务下线"
        
    finally:
        await service1.stop()
        await service2.stop()
        await client.close()

@pytest.mark.asyncio
async def test_load_management(router, router_address, zmq_context):
    """测试负载管理：满载报告、负载转移、满载恢复"""
    service1 = EchoService(router_address, context=zmq_context, max_concurrent=10)
    service2 = EchoService(router_address, context=zmq_context, max_concurrent=10)
    client = ClientDealer(router_address, context=zmq_context)
    
    try:
        await service1.start()
        await service2.start()
        await asyncio.sleep(0.1)
        
        # 1. 创建请求使一个服务接近满载
        async def slow_request(i: int):
            async for response in client.call_service("echo", f"test_{i}"):
                await asyncio.sleep(0.1)
                assert response == f"test_{i}"
                break
        
        # 发送请求使service1达到满载阈值
        overload_tasks = [slow_request(i) for i in range(8)]  # 80% * 10 = 8
        await asyncio.sleep(0.2)
        
        # 2. 验证负载转移
        for i in range(5):  # 发送额外请求，应该被路由到service2
            async for response in client.call_service("echo", f"new_{i}"):
                assert response == f"new_{i}"
                break
        
        # 3. 等待请求完成，验证满载恢复
        await asyncio.gather(*overload_tasks)
        await asyncio.sleep(0.2)
        
        services = await client.discover_services()
        states = [info.get('state') for info in services.values()]
        assert all(state == 'active' for state in states), "所有服务应该处于活跃状态"
        
    finally:
        await service1.stop()
        await service2.stop()
        await client.close()

@pytest.mark.asyncio
async def test_custom_load_strategy(router, router_address, zmq_context):
    """测试自定义负载策略"""
    class CustomService(EchoService):
        def check_overload(self) -> bool:
            return self._current_load >= self._max_concurrent * 0.5
        
        def check_can_resume(self) -> bool:
            return self._current_load <= self._max_concurrent * 0.3
    
    service = CustomService(router_address, context=zmq_context, max_concurrent=10)
    client = ClientDealer(router_address, context=zmq_context)
    
    try:
        await service.start()
        await asyncio.sleep(0.1)
        
        # 1. 测试自定义满载阈值
        tasks = []
        for i in range(6):  # 超过50%阈值
            task = asyncio.create_task(client.call_service("echo", f"test_{i}").__anext__())
            tasks.append(task)
        
        await asyncio.sleep(0.2)
        
        # 验证服务状态
        services = await client.discover_services()
        service_info = next(iter(services.values()))
        assert service_info['state'] == 'overload'
        
        # 2. 测试自定义恢复阈值
        results = await asyncio.gather(*tasks)
        await asyncio.sleep(0.2)
        
        services = await client.discover_services()
        service_info = next(iter(services.values()))
        assert service_info['state'] == 'active'
        
    finally:
        await service.stop()
        await client.close()