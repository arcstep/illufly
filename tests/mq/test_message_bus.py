import pytest
import asyncio
import zmq.asyncio
import logging
import os
from illufly.mq.message_bus import (
    MessageBusType, 
    create_message_bus,
    InprocMessageBus,
    IpcMessageBus,
    TcpMessageBus
)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@pytest.fixture(autouse=True)
def setup_logging(caplog):
    caplog.set_level(logging.DEBUG)

@pytest.fixture
async def inproc_bus():
    """进程内消息总线测试夹具"""
    bus = create_message_bus(MessageBusType.INPROC)
    yield bus
    bus.cleanup()

@pytest.fixture
async def ipc_pair():
    """IPC服务器/客户端对测试夹具"""
    ipc_path = "/tmp/illufly_test_pair.ipc"
    server = create_message_bus(
        MessageBusType.IPC, 
        path=ipc_path,
        role="server"
    )
    client = create_message_bus(
        MessageBusType.IPC,
        path=ipc_path,
        role="client"
    )
    server.start()
    client.start()
    yield server, client
    server.cleanup()
    client.cleanup()

@pytest.fixture
async def tcp_pair():
    """TCP服务器/客户端对测试夹具"""
    server = create_message_bus(
        MessageBusType.TCP, 
        host="127.0.0.1", 
        port=5555,
        role="server"
    )
    client = create_message_bus(
        MessageBusType.TCP, 
        host="127.0.0.1", 
        port=5555,
        role="client"
    )
    server.start()
    client.start()
    yield server, client
    server.cleanup()
    client.cleanup()

class TestInprocMessageBus:
    @pytest.mark.asyncio
    async def test_singleton_pattern(self):
        """测试进程内消息总线的单例模式"""
        bus1 = create_message_bus(MessageBusType.INPROC)
        bus2 = create_message_bus(MessageBusType.INPROC)
        assert bus1 is bus2

    @pytest.mark.asyncio
    async def test_auto_start(self, inproc_bus):
        """测试自动启动功能"""
        assert not inproc_bus._started
        await inproc_bus.publish("test", {"msg": "hello"})
        assert inproc_bus._started

    @pytest.mark.asyncio
    async def test_pub_sub(self, inproc_bus):
        """测试发布订阅功能"""
        test_message = {"msg": "hello"}
        received_messages = []

        async def subscriber():
            async for message in inproc_bus.subscribe(["test"]):
                received_messages.append(message)
                break

        # 启动订阅任务
        sub_task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.1)  # 等待订阅建立
        
        # 发布消息
        await inproc_bus.publish("test", test_message)
        
        # 等待接收
        await asyncio.wait_for(sub_task, timeout=1.0)
        assert received_messages[0] == test_message

class TestDistributedMessageBus:
    @pytest.mark.asyncio
    async def test_ipc_pub_sub(self, ipc_pair):
        """测试IPC模式的发布订阅"""
        server, client = ipc_pair
        test_message = {"msg": "hello"}
        received_messages = []

        async def subscriber():
            async for message in client.subscribe(["test"]):
                received_messages.append(message)
                break

        sub_task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.1)
        
        await server.publish("test", test_message)
        
        await asyncio.wait_for(sub_task, timeout=1.0)
        assert received_messages[0] == test_message

    @pytest.mark.asyncio
    async def test_tcp_pub_sub(self, tcp_pair):
        """测试TCP模式的发布订阅"""
        server, client = tcp_pair
        test_message = {"msg": "hello"}
        received_messages = []

        async def subscriber():
            async for message in client.subscribe(["test"]):
                received_messages.append(message)
                break

        sub_task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.1)
        
        await server.publish("test", test_message)
        
        await asyncio.wait_for(sub_task, timeout=1.0)
        assert received_messages[0] == test_message

    @pytest.mark.asyncio
    async def test_explicit_start_required(self):
        """测试分布式模式需要显式启动"""
        server = create_message_bus(MessageBusType.IPC, role="server")
        with pytest.raises(RuntimeError):
            await server.publish("test", {"msg": "hello"})

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self, tcp_pair):
        """测试多订阅者场景"""
        server, client = tcp_pair
        test_message = {"msg": "hello"}
        received_count = 0

        async def subscriber(id: int):
            nonlocal received_count
            async for message in client.subscribe(["test"]):
                assert message == test_message
                received_count += 1
                break

        # 创建多个订阅者
        tasks = [
            asyncio.create_task(subscriber(i))
            for i in range(3)
        ]
        
        await asyncio.sleep(0.1)
        await server.publish("test", test_message)
        
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=1.0)
        assert received_count == 3

    @pytest.mark.asyncio
    async def test_cleanup(self, tmp_path):
        """测试IPC清理功能"""
        ipc_path = "/tmp/illufly_test.ipc"
        server = create_message_bus(
            MessageBusType.IPC,
            path=ipc_path,
            role="server"
        )
        server.start()
        assert os.path.exists(ipc_path)
        server.cleanup()
        assert not os.path.exists(ipc_path) 