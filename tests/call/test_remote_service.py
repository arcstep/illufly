import pytest
import asyncio
import logging

logger = logging.getLogger(__name__)

from illufly.call import RemoteServer, RemoteClient
from illufly.mq import BlockType, Publisher

class EchoServer(RemoteServer):
    """简单的回显服务，用于测试"""
    async def _async_handler(self, *args, thread_id: str, publisher, **kwargs):
        """简单的回显处理函数"""
        await asyncio.sleep(0.5)
        publisher.text_chunk(thread_id, f"Echo: {args} {kwargs}")

class TestRemoteService:
    @pytest.fixture
    def service_config(self):
        """服务配置"""
        return {
            "publisher_address": "tcp://127.0.0.1:5555",
            "subscriber_address": "tcp://127.0.0.1:5555",
            "server_address": "tcp://127.0.0.1:5556",
            "service_name": "test_service"
        }

    @pytest.fixture
    async def server(self, service_config):
        """创建服务端"""
        server = EchoServer(
            address=service_config["server_address"],
            service_name=service_config["service_name"],
            publisher=Publisher(address=service_config["publisher_address"]),
            max_concurrent_tasks=100
        )
        yield server
        await server.stop()

    @pytest.fixture
    async def client(self, service_config):
        """创建客户端"""
        client = RemoteClient(
            server_address=service_config["server_address"]
        )
        yield client

    @pytest.mark.asyncio
    async def test_basic_communication(self, client, server, service_config):
        try:
            sub = await client.async_call("hello", "world")
            response = list(sub.collect())
            logger.info(f"response: {response}")
            assert response[0].block_type == BlockType.TEXT_CHUNK
            assert "world" in response[0].text
            assert response[-1].block_type == BlockType.END
        except asyncio.TimeoutError:
            pytest.fail("Request timed out")

    @pytest.mark.asyncio
    async def test_simple_mode(self, service_config):
        """测试错误处理"""
        class SimpleServer(RemoteServer):
            async def _async_handler(self, *args, thread_id: str, publisher: Publisher, **kwargs):
                await asyncio.sleep(0.5)
                publisher.text_chunk(thread_id, f"Echo: {args} {kwargs}")

        simple = SimpleServer()        

        sub = await simple.async_call("test")
        responses = list(sub.collect())
        assert responses[0].block_type == BlockType.TEXT_CHUNK
        assert "test" in responses[0].text
        assert responses[-1].block_type == BlockType.END

        # 重复调用
        sub = await simple.async_call("test")
        responses = list(sub.collect())
        assert responses[0].block_type == BlockType.TEXT_CHUNK
        assert "test" in responses[0].text
        assert responses[-1].block_type == BlockType.END

        await simple.stop()

    def test_sync_call(self, server, client):
        """测试同步调用"""
        test_args = ["sync_test"]
        test_kwargs = {"sync": True}
        
        sub = client.call(*test_args, **test_kwargs)
        response = list(sub.collect())
        
        assert response[0].block_type == BlockType.TEXT_CHUNK
        assert "sync_test" in response[0].text
        assert response[-1].block_type == BlockType.END

    @pytest.mark.asyncio
    async def test_concurrent_communication(self, server, service_config):
        """测试并发通信"""
        await asyncio.sleep(0.1)
        # 等待服务端完全启动
        async def make_call(i):
            client = RemoteClient(server_address=service_config["server_address"])
            return await client.async_call(message=f"message_{i}")

        # 创建10个并发调用
        tasks = [make_call(i) for i in range(10)]
        subs = await asyncio.gather(*tasks)
        
        # 验证每个调用的结果
        for sub in subs:
            response = list(sub.collect())
            logger.info(f"response: {response}")
            
            # 验证基本结构
            assert len(response) >= 2  # 至少有一个文本块和一个结束块
            assert response[0].block_type == BlockType.TEXT_CHUNK
            assert response[-1].block_type == BlockType.END

    @pytest.mark.asyncio
    async def test_timeout(self, service_config):
        """测试超时情况"""
        class SlowServer(RemoteServer):
            async def _async_handler(self, *args, thread_id: str, publisher, **kwargs):
                await asyncio.sleep(10)  # 模拟慢处理
                return {"result": "timeout"}

        server = SlowServer(
            address=service_config["server_address"],
            service_name=service_config["service_name"],
            publisher=Publisher(address=service_config["publisher_address"])
        )

        try:
            client = RemoteClient(
                server_address=service_config["server_address"],
                timeout=500  # 设置较短的超时时间
            )

            sub = await client.async_call("test")
            async for block in sub.async_collect():
                if block.is_error:
                    assert "timeout" in block.error.lower()
                    break
            else:
                pytest.fail("Expected timeout error")

        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_error_handling(self, service_config):
        """测试错误处理"""
        class ErrorServer(RemoteServer):
            async def _async_handler(self, *args, thread_id: str, publisher: Publisher, **kwargs):
                raise ValueError("测试错误")

        server = ErrorServer(
            address=service_config["server_address"],
            service_name=service_config["service_name"],
            publisher=Publisher(address=service_config["publisher_address"])
        )        
        client = RemoteClient(
            server_address=service_config["server_address"]
        )

        sub = await client.async_call("test")
        responses = list(sub.collect())
        assert responses[0].is_error
        assert "测试错误" in responses[0].error

        await server.stop()

