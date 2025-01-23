import pytest
import asyncio
import zmq.asyncio
from illufly.mq.router import RouterDevice
from illufly.mq.reqrep import Requester, Replier
from illufly.mq.pubsub import Publisher

class TestRouterDevice:
    @pytest.fixture
    def frontend_address(self):
        return "inproc://frontend"
        
    @pytest.fixture
    def backend_address(self):
        return "inproc://backend"
    
    @pytest.fixture
    def message_bus(self):
        return Publisher("inproc://publisher")

    @pytest.mark.asyncio
    async def test_message_routing(self, frontend_address, backend_address, message_bus):
        """测试消息路由功能"""
        # 创建路由设备
        router = RouterDevice(frontend_address, backend_address)
        router_task = asyncio.create_task(router.start())
        
        # 创建后端服务
        async def echo_handler(*args, thread_id, publisher, **kwargs):
            publisher.text_chunk(thread_id, "echo")
        
        replier = Replier(backend_address, publisher=message_bus, connect_mode=True)
        replier_task = asyncio.create_task(replier.async_reply(echo_handler))
        
        try:
            # 创建前端客户端
            requester = Requester(frontend_address)
            
            # 发送请求并验证响应
            sub = await requester.async_request()
            responses = list(sub.collect())
            
            assert any(block.text == "echo" for block in responses)
            
        finally:
            router_task.cancel()
            replier_task.cancel()
            await asyncio.gather(
                router_task, replier_task, 
                return_exceptions=True
            )
            router.cleanup()
            replier.cleanup()

    @pytest.mark.asyncio
    async def test_multiple_repliers(self, frontend_address, backend_address, message_bus):
        """测试多个后端服务的负载均衡"""
        router = RouterDevice(frontend_address, backend_address)
        router_task = asyncio.create_task(router.start())
        
        # 创建多个后端服务
        repliers = []
        replier_tasks = []
        
        async def worker_handler(*args, thread_id, publisher, **kwargs):
            publisher.text_chunk(thread_id, f"worker")
        
        for i in range(3):
            replier = Replier(backend_address, publisher=message_bus, connect_mode=True)
            repliers.append(replier)
            task = asyncio.create_task(replier.async_reply(worker_handler))
            replier_tasks.append(task)
        
        try:
            # 发送多个请求
            requester = Requester(frontend_address)
            responses = []
            
            for _ in range(5):
                sub = await requester.async_request()
                responses.append(list(sub.collect()))
            
            # 验证所有请求都得到了响应
            assert all(
                any(block.text == "worker" for block in resp)
                for resp in responses
            )
            
        finally:
            router_task.cancel()
            for task in replier_tasks:
                task.cancel()
            await asyncio.gather(
                router_task, *replier_tasks,
                return_exceptions=True
            )
            router.cleanup()
            for replier in repliers:
                replier.cleanup() 