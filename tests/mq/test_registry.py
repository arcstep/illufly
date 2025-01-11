import pytest
import logging
from illufly.mq.base import MQBus
from illufly.mq.registry import RegistryClient
from illufly.mq.types import ServiceMode

logger = logging.getLogger(__name__)

@pytest.fixture
async def mq_bus(caplog):
    """创建MQ总线实例"""
    caplog.set_level(logging.INFO)
    bus = MQBus(mode=MQBus.MODE_INPROC, logger=logger)
    bus.start()
    try:
        yield bus
    finally:
        bus.stop()

@pytest.fixture
async def registry_client(mq_bus):
    """创建注册中心客户端"""
    client = RegistryClient(mode="inproc", logger=logger)
    await client.verify_connection()  # 异步验证连接
    try:
        yield client
    finally:
        await client.close()

@pytest.mark.asyncio
async def test_invalid_connection():
    """测试无效连接"""
    client = RegistryClient(mode="tcp", host="invalid_host", port=9999)
    with pytest.raises(ConnectionError):
        await client.verify_connection()

@pytest.mark.asyncio
async def test_register_service(mq_bus, registry_client):
    """测试服务注册"""
    response = await registry_client.register_service(
        name="test_service",
        methods={
            "test_method": "Test Method Description",
            "stream_method": "Stream Method Description"
        },
        service_mode=ServiceMode.PUSH_PULL
    )
    
    assert response.status == "success"
    assert "test_service" in response.message
    
    # 验证服务是否真的注册了
    service_info = await registry_client.discover_service("test_service")
    assert service_info.name == "test_service"
    assert service_info.address == "inproc://test_service"
    assert service_info.service_mode == ServiceMode.PUSH_PULL
    assert "test_method" in service_info.methods

@pytest.mark.asyncio
async def test_list_services(mq_bus, registry_client):
    """测试列出服务"""
    # 先注册两个服务
    await registry_client.register_service(
        name="service1",
        methods={"method1": "desc1"}
    )
    await registry_client.register_service(
        name="service2",
        methods={"method2": "desc2"}
    )
    
    # 获取服务列表
    services = await registry_client.list_services()
    assert len(services) == 2
    service_names = {s.name for s in services}
    assert service_names == {"service1", "service2"}

@pytest.mark.asyncio
async def test_heartbeat(mq_bus, registry_client):
    """测试心跳功能"""
    # 先注册服务
    await registry_client.register_service(
        name="heartbeat_service",
        methods={"method": "desc"}
    )
    
    # 发送心跳
    response = await registry_client.send_heartbeat("heartbeat_service")
    assert response.status == "success"
    
    # 验证服务仍然存在
    service_info = await registry_client.discover_service("heartbeat_service")
    assert service_info.name == "heartbeat_service"

@pytest.mark.asyncio
async def test_register_duplicate_service(mq_bus, registry_client):
    """测试重复注册服务"""
    # 第一次注册
    await registry_client.register_service(
        name="duplicate_service",
        methods={"method": "desc1"}
    )
    
    # 第二次注册（更新）
    response = await registry_client.register_service(
        name="duplicate_service",
        methods={"method": "desc2"}
    )
    
    assert response.status == "success"
    
    # 验证服务信息已更新
    service_info = await registry_client.discover_service("duplicate_service")
    assert service_info.address == "inproc://duplicate_service"
