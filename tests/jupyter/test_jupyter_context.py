import pytest
import asyncio
from illufly.base.base_call import BaseCall
from illufly.mq.req_rep_service import ReqRepService

# 模拟 Jupyter 环境
@pytest.fixture
def jupyter_context(monkeypatch):
    """模拟 Jupyter 环境的 fixture"""
    def mock_is_jupyter(self):
        return True
    
    monkeypatch.setattr(BaseCall, "_is_jupyter_cell", mock_is_jupyter)
    
    # 确保有事件循环
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    yield loop
    
    # 清理
    try:
        loop.close()
    except Exception:
        pass
    asyncio.set_event_loop(None)

class TestBaseCallInJupyter:
    """测试 BaseCall 在 Jupyter 环境中的行为"""
    
    class SyncHandler(BaseCall):
        def handle_call(self, value):
            return f"sync: {value}"
    
    def test_sync_call(self, jupyter_context):
        """测试同步调用 - 不使用 asyncio 标记"""
        handler = self.SyncHandler()
        result = handler("test")
        assert result == "sync: test"
    
    @pytest.mark.asyncio
    async def test_async_call(self, jupyter_context):
        """测试异步调用"""
        handler = self.SyncHandler()
        result = await handler("test")
        assert result == "sync: test"
    
    @pytest.mark.asyncio
    async def test_direct_await(self, jupyter_context):
        """测试直接使用 await"""
        handler = self.SyncHandler()
        result = await handler("test")
        assert result == "sync: test"

class TestReqRepServiceInJupyter:
    """测试 ReqRepService 在 Jupyter 环境中的行为"""
    
    class MyService(ReqRepService):
        def handle_request(self, value):
            return f"processed: {value}"
    
    @pytest.mark.asyncio
    async def test_service_call(self, jupyter_context):
        """测试服务调用"""
        ms = self.MyService()
        try:
            # 在异步上下文中使用 await
            result = await ms("hello")
            assert isinstance(result, dict)
            assert "request_id" in result
        finally:
            # 确保服务正确关闭
            if hasattr(ms, 'stop'):
                await ms.stop()
            # 等待一小段时间确保资源释放
            await asyncio.sleep(0.1) 