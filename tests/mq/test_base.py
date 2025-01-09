import pytest
import zmq
import logging
from illufly.mq.base import MQBus, ServiceStatus, RegistryRequest, RegistryResponse

print("测试模块开始加载...")  # 直接打印，确认模块是否被加载

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_basic_setup():
    """最基础的测试，确认测试框架是否正常工作"""
    print("运行基础测试...")
    logger.info("运行基础测试...")
    assert True

@pytest.mark.basic
def test_mq_bus_init():
    """测试MQ总线初始化"""
    print("测试MQ总线初始化...")
    logger.info("测试MQ总线初始化...")
    bus = MQBus(mode=MQBus.MODE_INPROC)
    assert bus is not None
    assert bus.mode == MQBus.MODE_INPROC

@pytest.fixture(autouse=True)
def setup_logging(caplog):
    caplog.set_level(logging.INFO)

@pytest.fixture
def mq_bus(caplog):
    """创建MQ总线实例"""
    caplog.set_level(logging.INFO)
    logger.info("创建MQ总线实例")
    bus = MQBus(mode=MQBus.MODE_INPROC)
    logger.info("MQ总线实例创建完成")
    bus.start()  # 确保在使用前启动总线
    yield bus
    logger.info("关闭MQ总线")
    bus.stop()

@pytest.fixture
def registry_client(caplog):
    """创建注册中心客户端"""
    logger.info("创建注册中心客户端")
    context = zmq.Context.instance()  # 使用相同的Context实例
    socket = context.socket(zmq.REQ)
    socket.setsockopt(zmq.LINGER, 0)
    socket.setsockopt(zmq.RCVTIMEO, 1000)  # 1秒超时
    socket.setsockopt(zmq.SNDTIMEO, 1000)  # 1秒超时
    socket.connect(MQBus.INPROC_REGISTRY)
    logger.info("注册中心客户端连接成功")
    yield socket
    logger.info("关闭注册中心客户端")
    socket.close()

def test_service_registration(mq_bus, registry_client, caplog):
    """测试服务注册功能"""
    caplog.set_level(logging.INFO)
    logger.info("开始测试服务注册功能")
    
    # 发送注册请求
    request = RegistryRequest(
        action="register",
        service="test_service",
        methods={"test_method": "Test Method Description"},
        address="test_address"
    )
    logger.info(f"发送注册请求: {request}")
    
    # 确保发送成功
    try:
        registry_client.send_json(request.model_dump())
        logger.info("请求已发送，等待响应...")
        
        # 接收响应
        response = registry_client.recv_json()
        logger.info(f"收到响应: {response}")
        response = RegistryResponse.model_validate(response)
        
        assert response.status == "success"
        assert "test_service" in response.message
        
    except zmq.error.Again:
        logger.error("请求超时")
        raise
    except Exception as e:
        logger.error(f"请求失败: {e}")
        raise

def test_service_discovery(mq_bus, registry_client):
    """测试服务发现功能"""
    # 先注册一个服务
    register_request = RegistryRequest(
        action="register",
        service="test_service",
        methods={"test_method": "description"},
        address="test_address"
    )
    registry_client.send_json(register_request.model_dump())
    registry_client.recv_json()  # 清除注册响应
    
    # 发送发现请求
    discover_request = RegistryRequest(
        action="discover",
        service="test_service"
    )
    registry_client.send_json(discover_request.model_dump())
    
    # 接收响应
    response = RegistryResponse.model_validate(
        registry_client.recv_json()
    )
    
    # 验证响应
    assert response.status == "success"
    assert response.data is not None
    assert "name" in response.data
    assert response.data["name"] == "test_service"
    assert response.data["address"] == "test_address"
    assert "test_method" in response.data["methods"]

def test_service_heartbeat(mq_bus, registry_client):
    """测试服务心跳功能"""
    # 先注册服务
    register_request = RegistryRequest(
        action="register",
        service="test_service",
        methods={},
        address="test_address"
    )
    registry_client.send_json(register_request.model_dump())
    registry_client.recv_json()  # 清除注册响应
    
    # 发送心跳
    heartbeat_request = RegistryRequest(
        action="heartbeat",
        service="test_service"
    )
    registry_client.send_json(heartbeat_request.model_dump())
    
    # 验证心跳响应
    response = RegistryResponse.model_validate(
        registry_client.recv_json()
    )
    assert response.status == "success"
    
    # 验证服务状态
    service_info = mq_bus.get_service_info("test_service")
    assert service_info.status == ServiceStatus.ACTIVE

def test_service_unregister(mq_bus, registry_client):
    """测试服务注销功能"""
    # 先注册服务
    register_request = RegistryRequest(
        action="register",
        service="test_service",
        methods={},
        address="test_address"
    )
    registry_client.send_json(register_request.model_dump())
    registry_client.recv_json()  # 清除注册响应
    
    # 发送注销请求
    unregister_request = RegistryRequest(
        action="unregister",
        service="test_service"
    )
    registry_client.send_json(unregister_request.model_dump())
    
    # 验证注销响应
    response = RegistryResponse.model_validate(
        registry_client.recv_json()
    )
    assert response.status == "success"
    
    # 验证服务已被移除
    assert mq_bus.get_service_info("test_service") is None

def test_list_active_services(mq_bus, registry_client):
    """测试列出活跃服务功能"""
    # 注册多个服务
    services = ["service1", "service2", "service3"]
    for service in services:
        request = RegistryRequest(
            action="register",
            service=service,
            methods={},
            address=f"{service}_address"
        )
        registry_client.send_json(request.model_dump())
        registry_client.recv_json()  # 清除响应
    
    # 获取活跃服务列表
    active_services = mq_bus.list_services()
    
    # 验证所有服务都在列表中
    assert len(active_services) == len(services)
    for service in services:
        assert service in active_services 