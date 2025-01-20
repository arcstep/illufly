import pytest
import asyncio
import os
import tempfile
from illufly.mq.req import Requester
from illufly.mq.rep import Replier
from illufly.mq.models import StreamingBlock, BlockType

class TestReqRep:
    @pytest.fixture
    def temp_ipc_path(self):
        """创建临时IPC文件路径"""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            path = tmp.name
        yield f"ipc://{path}"
        # 清理
        if os.path.exists(path):
            os.unlink(path)

    @pytest.fixture
    def tcp_address(self):
        """获取可用的TCP地址"""
        return "tcp://127.0.0.1:5555"

    @pytest.fixture
    def inproc_address(self):
        """获取进程内通信地址"""
        return "inproc://test"

    async def echo_handler(self, data):
        """简单的回显处理函数"""
        return data

    async def async_test_communication(self, address):
        """测试基本通信"""
        # 创建服务端和客户端
        replier = Replier(address=address)
        requester = Requester(address=address)

        # 启动服务端（在后台运行）
        server_task = asyncio.create_task(replier.async_reply(self.echo_handler))
        
        try:
            # 发送测试数据
            test_data = {"message": "hello world"}
            response = await requester.async_request(test_data)
            
            assert response is not None
            assert isinstance(response, StreamingBlock)
            assert response.content == test_data
            
        finally:
            # 清理
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass
            replier.cleanup()
            requester.cleanup()

    @pytest.mark.asyncio
    async def test_inproc_communication(self, inproc_address):
        """测试进程内通信"""
        await self.async_test_communication(inproc_address)

    @pytest.mark.asyncio
    async def test_ipc_communication(self, temp_ipc_path):
        """测试IPC通信"""
        await self.async_test_communication(temp_ipc_path)

    @pytest.mark.asyncio
    async def test_tcp_communication(self, tcp_address):
        """测试TCP通信"""
        await self.async_test_communication(tcp_address)

    @pytest.mark.asyncio
    async def test_timeout(self, tcp_address):
        """测试请求超时"""
        async def slow_handler(data):
            await asyncio.sleep(2)
            return data

        replier = Replier(address=tcp_address)
        requester = Requester(address=tcp_address)

        server_task = asyncio.create_task(replier.async_reply(slow_handler))
        
        try:
            # 设置较短的超时时间
            response = await requester.async_request({"test": "data"}, timeout=0.1)
            
            assert response is not None
            assert response.block_type == BlockType.ERROR
            assert "timeout" in response.content.lower()
            
        finally:
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass
            replier.cleanup()
            requester.cleanup()

    @pytest.mark.asyncio
    async def test_error_handling(self, tcp_address):
        """测试错误处理"""
        async def error_handler(data):
            raise ValueError("测试错误")

        replier = Replier(address=tcp_address)
        requester = Requester(address=tcp_address)

        server_task = asyncio.create_task(replier.async_reply(error_handler))
        
        try:
            response = await requester.async_request({"test": "data"})
            
            assert response is not None
            assert response.block_type == BlockType.ERROR
            assert "测试错误" in response.content
            
        finally:
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass
            replier.cleanup()
            requester.cleanup() 