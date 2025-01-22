import pytest
import asyncio
import os
import tempfile
import logging

from illufly.mq.pubsub import Publisher
from illufly.mq.reqrep import Requester, Replier
from illufly.mq.models import BlockType, ReplyBlock, ReplyState

logger = logging.getLogger(__name__)

class TestReqRep:
    @pytest.fixture(autouse=True)
    def setup_logger(self, caplog):
        """设置日志记录器"""
        caplog.set_level(logging.DEBUG)

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

    async def echo_handler(self, message: str, thread_id: str, publisher: Publisher, **kwargs):
        """简单的回显处理函数"""
        echo_message = f"echo: {message}"
        logger.info(f"echo_handler input: {echo_message}, {kwargs}")
        publisher.text_chunk(thread_id, echo_message)
        return echo_message

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
            sub = await requester.async_request(
                kwargs={"message": "hello world"}
            )
            response = list(sub.collect())
            logger.info(f"first response: {response}")
            assert len(response) == 2
            assert 'hello world' in response[0].content
            assert response[0].block_type == BlockType.TEXT_CHUNK
            assert response[1].block_type == BlockType.END

            # 再次发送测试数据
            test_data = {"message": "hello world 2"}
            sub = await requester.async_request(
                kwargs={"message": "hello world 2"}
            )
            response = list(sub.collect())
            logger.info(f"second response: {response}")
            assert len(response) == 2
            assert 'hello world 2' in response[0].content

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
        async def slow_handler(message: str):
            await asyncio.sleep(2)
            return message

        replier = Replier(address=tcp_address)

        # 设置较短的超时时间
        requester = Requester(address=tcp_address, timeout=100)

        server_task = asyncio.create_task(replier.async_reply(slow_handler))
        
        try:
            sub = await requester.async_request(
                kwargs={"message": "hello world"}
            )
            response = list(sub.collect())
            logger.info(f"timeout response: {response}")
            assert len(response) == 2
            assert "timeout" in response[0].content.lower()
            
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
        async def error_handler(message: str, thread_id: str, publisher: Publisher, **kwargs):
            raise ValueError("测试错误")

        replier = Replier(address=tcp_address)
        requester = Requester(address=tcp_address)

        server_task = asyncio.create_task(replier.async_reply(error_handler))
        
        try:
            sub = await requester.async_request(
                kwargs={"message": "hello world"}
            )
            response = list(sub.collect())
            logger.info(f"error response: {response}")
            assert len(response) == 2
            assert response[0].block_type == BlockType.ERROR
            assert "测试错误" in response[0].content
            
        finally:
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass
            replier.cleanup()
            requester.cleanup()

    @pytest.mark.asyncio
    async def test_concurrent_limit(self, inproc_address):
        """测试并发限制"""
        max_tasks = 3
        replier = Replier(
            address=inproc_address, 
            max_concurrent_tasks=max_tasks
        )
        requester = Requester(address=inproc_address)
        
        async def slow_handler(*args, thread_id: str, publisher: Publisher, **kwargs):
            publisher.text_chunk(thread_id, "Start")
            await asyncio.sleep(0.5)
            publisher.text_chunk(thread_id, "End")
        
        server_task = asyncio.create_task(replier.async_reply(slow_handler))
        
        try:
            # 发送超过限制的并发请求
            tasks = []
            for _ in range(max_tasks + 2):
                sub = await requester.async_request()
                tasks.append(sub)
            
            # 验证实际并发数不超过限制
            assert len(replier._pending_tasks) <= max_tasks
            
        finally:
            server_task.cancel()
            await server_task
            replier.cleanup()
            requester.cleanup()

    @pytest.mark.asyncio
    async def test_task_cleanup(self, inproc_address):
        """测试任务清理"""
        replier = Replier(address=inproc_address)
        requester = Requester(address=inproc_address)
        
        async def simple_handler(*args, thread_id: str, publisher: Publisher, **kwargs):
            publisher.text_chunk(thread_id, "Start")
            await asyncio.sleep(0.1)
            publisher.text_chunk(thread_id, "End")
        
        server_task = asyncio.create_task(replier.async_reply(simple_handler))
        
        try:
            # 发送请求
            sub = await requester.async_request()
            
            # 取消服务
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass  # 预期会收到取消异常
            
            # 验证任务被清理
            assert len(replier._pending_tasks) == 0
            
        finally:
            replier.cleanup()
            requester.cleanup() 