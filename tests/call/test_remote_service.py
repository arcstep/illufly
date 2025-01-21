import pytest
import asyncio
import logging

logger = logging.getLogger(__name__)

from illufly.call import RemoteServer, RemoteClient
from illufly.mq import BlockType

class EchoServer(RemoteServer):
    async def _async_handler(self, *args, thread_id: str, publisher, **kwargs):
        """简单的回显处理函数"""
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
            service_name=service_config["service_name"],
            publisher_address=service_config["publisher_address"],
            server_address=service_config["server_address"]
        )
        yield server
        await server.async_cleanup()  # 使用异步清理

    @pytest.fixture
    async def client(self, service_config):
        """创建客户端"""
        client = RemoteClient(
            service_name=service_config["service_name"],
            subscriber_address=service_config["subscriber_address"],
            server_address=service_config["server_address"]
        )
        yield client
        # 清理客户端资源
        if hasattr(client, '_server'):
            client._server.cleanup()
        if hasattr(client, '_subscriber'):
            client._subscriber.cleanup()

    @pytest.mark.asyncio
    async def test_basic_communication(self, server, client):
        """测试基本通信"""
        sub = await client.async_call(thread_id="test_thread_id", hello="world")
        response = list(sub.collect())
        
        logger.info(f"response: {response}")
        assert response[0].block_type == BlockType.TEXT_CHUNK
        assert "world" in response[0].text
        assert response[-1].block_type == BlockType.END

    @pytest.mark.asyncio
    async def test_concurrent_communication(self, server, service_config):
        """测试并发通信"""
        # 等待服务端完全启动
        await asyncio.sleep(0.1)
        
        async def make_call(i):
            client = RemoteClient(
                service_name=service_config["service_name"],
                subscriber_address=service_config["subscriber_address"],
                server_address=service_config["server_address"]
            )            

            thread_id = f"test_thread_{i}"
            message = f"message_{i}"
            sub = await client.async_call(
                thread_id=thread_id,
                message=message
            )
            return thread_id, sub

        # 创建10个并发调用
        tasks = [make_call(i) for i in range(10)]
        results = await asyncio.gather(*tasks)
        
        # 验证每个调用的结果
        for thread_id, sub in results:
            response = list(sub.collect())
            logger.info(f"Thread {thread_id} response: {response}")
            
            # 验证基本结构
            assert len(response) >= 2  # 至少有一个文本块和一个结束块
            assert response[0].block_type == BlockType.TEXT_CHUNK
            assert response[-1].block_type == BlockType.END
            
            # 验证内容匹配
            thread_num = thread_id.split('_')[-1]
            assert f"message_{thread_num}" in response[0].text
            
            # 验证 thread_id 正确
            for block in response:
                assert block.thread_id == thread_id

    @pytest.mark.asyncio
    async def test_timeout(self, service_config):
        """测试超时情况"""
        class SlowServer(RemoteServer):
            async def _async_handler(self, *args, thread_id: str, publisher, **kwargs):
                await asyncio.sleep(2)  # 模拟慢处理
                return {"result": "timeout"}

        server = SlowServer(
            service_name=service_config["service_name"],
            publisher_address=service_config["publisher_address"],
            server_address=service_config["server_address"]
        )

        client = RemoteClient(
            service_name=service_config["service_name"],
            subscriber_address=service_config["subscriber_address"],
            server_address=service_config["server_address"],
            timeout=1000  # 设置较短的超时时间
        )

        sub = await client.async_call("test")
        response = list(sub.collect())
        logger.info(f"response: {response}")
        
        assert response[0].block_type == BlockType.ERROR
        assert "timeout" in response[0].error

        server.cleanup()

    @pytest.mark.asyncio
    async def test_error_handling(self, service_config):
        """测试错误处理"""
        class ErrorServer(RemoteServer):
            async def _async_handler(self, *args, thread_id: str, publisher, **kwargs):
                raise ValueError("测试错误")

        server = ErrorServer(
            service_name=service_config["service_name"],
            publisher_address=service_config["publisher_address"],
            server_address=service_config["server_address"]
        )

        client = RemoteClient(
            service_name=service_config["service_name"],
            subscriber_address=service_config["subscriber_address"],
            server_address=service_config["server_address"]
        )

        with pytest.raises(Exception) as exc_info:
            await client.async_call("test")
        
        assert "测试错误" in str(exc_info.value)

        server.cleanup()

    def test_sync_call(self, server, client):
        """测试同步调用"""
        test_args = ("sync_test",)
        test_kwargs = {"sync": True}
        
        response = client.call(*test_args, **test_kwargs)
        
        assert response["args"] == test_args
        assert response["kwargs"]["sync"] == test_kwargs["sync"] 