import pytest
from illufly.base.base_service import BaseService
from illufly.mq.message_bus import MessageBus

class MyService(BaseService):
    """用于测试的服务类"""
    def __init__(self, service_name: str = "test_service", message_bus_address: str = None):
        super().__init__(service_name, message_bus_address)
        self.register_method("server", async_handle=self._async_handler)
    
    async def _async_handler(self, message: str, thread_id: str, message_bus: MessageBus):
        """异步处理器"""
        response = {"status": "success", "message": f"收到消息: {message}"}
        message_bus.publish(thread_id, response)
        return response

class TestBaseService:
    @pytest.fixture
    def service(self):
        """创建测试服务实例"""
        return MyService()
    
    def test_sync_call(self, service):
        """测试同步调用"""
        resp = service.call(message="测试消息")
        # 直接迭代 Response 对象
        messages = list(resp)
        assert len(messages) > 0
        assert messages[0]["status"] == "success"
        assert messages[0]["message"] == "收到消息: 测试消息"
    
    @pytest.mark.asyncio
    async def test_async_call(self, service):
        """测试异步调用"""
        resp = await service.async_call(message="异步测试消息")
        # 使用异步迭代收集消息
        messages = []
        async for msg in resp:
            messages.append(msg)
        
        assert len(messages) > 0
        assert messages[0]["status"] == "success"
        assert messages[0]["message"] == "收到消息: 异步测试消息" 
