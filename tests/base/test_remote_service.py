import pytest
import asyncio
from illufly.base.remote_server import RemoteServer
from illufly.base.remote_client import RemoteClient
from illufly.mq import StreamingBlock

class EchoServer(RemoteServer):
    async def _async_handler(self, *args, thread_id: str, publisher, **kwargs):
        """简单的回显处理函数"""
        # 返回接收到的参数
        return {
            "args": args,
            "kwargs": kwargs
        }

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
        # 清理
        server.cleanup()

    @pytest.fixture
    async def client(self, service_config):
        """创建客户端"""
        client = RemoteClient(
            service_name=service_config["service_name"],
            subscriber_address=service_config["subscriber_address"],
            server_address=service_config["server_address"]
        )
        yield client
        # 清理

    @pytest.mark.asyncio
    async def test_basic_communication(self, server, client):
        """测试基本通信"""
        test_args = ("hello",)
        test_kwargs = {"world": 42}
        
        response = await client.async_call(*test_args, **test_kwargs)
        
        assert response["args"] == test_args
        assert response["kwargs"]["world"] == test_kwargs["world"]

    @pytest.mark.asyncio
    async def test_concurrent_calls(self, server, client):
        """测试并发调用"""
        async def make_call(i):
            return await client.async_call(f"call_{i}")

        # 创建多个并发调用
        tasks = [make_call(i) for i in range(5)]
        results = await asyncio.gather(*tasks)
        
        # 验证所有调用都成功完成
        for i, result in enumerate(results):
            assert result["args"][0] == f"call_{i}"

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
            timeout=1.0  # 设置较短的超时时间
        )

        with pytest.raises(Exception) as exc_info:
            await client.async_call("test")
        
        assert "timeout" in str(exc_info.value).lower()

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