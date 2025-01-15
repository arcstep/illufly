import pytest
import asyncio
from illufly.base.base_call import BaseCall

class SyncHandler(BaseCall):
    def __init__(self):
        super().__init__()
        self.register_methods("handle", sync_handle=self.handle_request)
        
    def handle_request(self, value):
        return f"sync: {value}"

class AsyncHandler(BaseCall):
    def __init__(self):
        super().__init__()
        self.register_methods("handle", async_handle=self.async_handle_request)
        
    async def async_handle_request(self, value):
        return f"async: {value}"

class BothHandler(BaseCall):
    def __init__(self):
        super().__init__()
        self.register_methods(
            "handle",
            sync_handle=self.handle_request,
            async_handle=self.async_handle_request
        )
        
    def handle_request(self, value):
        return f"sync: {value}"
        
    async def async_handle_request(self, value):
        return f"async: {value}"

def test_method_registration():
    """测试方法注册"""
    handler = BothHandler()
    
    # 测试重复注册
    with pytest.raises(ValueError):
        handler.register_methods("new", None, None)
    
    # 测试注册类型错误的方法
    async def wrong_sync():
        pass
    def wrong_async():
        pass
    
    with pytest.raises(ValueError):
        handler.register_methods("wrong", sync_handle=wrong_sync)
    with pytest.raises(ValueError):
        handler.register_methods("wrong", async_handle=wrong_async)
        
    # 测试调用未注册的方法
    with pytest.raises(KeyError):
        handler.sync_call("not_exists")

def test_sync_handler():
    """测试同步处理器"""
    handler = SyncHandler()
    
    # 使用 sync_call
    result = handler.sync_call("handle", "test")
    assert result == "sync: test"
    
    # 异步调用同步方法
    result = asyncio.run(handler.async_call("handle", "test"))
    assert result == "sync: test"

@pytest.mark.asyncio
async def test_async_handler():
    """测试异步处理器"""
    handler = AsyncHandler()
    
    # 使用 async_call
    result = await handler.async_call("handle", "test")
    assert result == "async: test"
    
    # 同步调用异步方法
    result = handler.sync_call("handle", "test")
    assert result == "async: test"

@pytest.mark.asyncio
async def test_both_handler():
    """测试双模式处理器"""
    handler = BothHandler()
    
    # 使用 sync_call
    result = handler.sync_call("handle", "test")
    assert result == "sync: test"
    
    # 使用 async_call
    result = await handler.async_call("handle", "test")
    assert result == "async: test"

@pytest.mark.asyncio
async def test_nested_event_loops():
    """测试嵌套事件循环场景"""
    handler = AsyncHandler()
    
    # 在异步上下文中使用 sync_call
    result1 = handler.sync_call("handle", "test1")
    assert result1 == "async: test1"
    
    # 在异步上下文中使用 async_call
    result2 = await handler.async_call("handle", "test2")
    assert result2 == "async: test2"
    
    # 在同步上下文中嵌套调用
    def sync_wrapper():
        return handler.sync_call("handle", "test3")
    
    result3 = sync_wrapper()
    assert result3 == "async: test3"
    
    # 在异步上下文中嵌套异步调用
    async def async_wrapper():
        return await handler.async_call("handle", "test4")
    
    result4 = await async_wrapper()
    assert result4 == "async: test4"

def test_sync_context():
    """测试纯同步上下文"""
    handler = AsyncHandler()
    
    # 在同步上下文中使用 sync_call
    result = handler.sync_call("handle", "test")
    assert result == "async: test"

@pytest.mark.asyncio
async def test_async_context():
    """测试纯异步上下文"""
    handler = AsyncHandler()
    
    # 在异步上下文中使用 async_call
    result = await handler.async_call("handle", "test")
    assert result == "async: test"
