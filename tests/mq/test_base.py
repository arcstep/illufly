import pytest
import logging
import zmq
from illufly.mq.base import MQBus, RegistryRequest, RegistryResponse

logger = logging.getLogger(__name__)

@pytest.fixture
async def mq_bus(caplog):
    """创建MQ总线实例"""
    caplog.set_level(logging.INFO)
    logger.info("创建MQ总线实例")
    bus = MQBus(mode=MQBus.MODE_INPROC, logger=logger)
    bus.start()
    yield bus
    logger.info("关闭MQ总线")
    bus.stop()

@pytest.mark.asyncio
async def test_service_registration(mq_bus, caplog):
    """测试服务注册功能"""
    caplog.set_level(logging.INFO)
    logger.info("开始测试服务注册功能")
    
    # 创建请求socket
    context = zmq.asyncio.Context.instance()
    socket = context.socket(zmq.REQ)
    socket.connect("inproc://registry")
    
    try:
        # 构造注册请求
        request = RegistryRequest(
            action="register",
            service="test_service",
            methods={"test_method": "Test Method Description"},
            address="inproc://test_service"
        )
        
        # 发送请求
        logger.info(f"发送注册请求: {request}")
        await socket.send_json(request.model_dump())
        
        # 接收响应
        response_data = await socket.recv_json()
        response = RegistryResponse.model_validate(response_data)
        logger.info(f"收到响应: {response}")
        
        # 验证响应
        assert response.status == "success"
        
    finally:
        socket.close() 