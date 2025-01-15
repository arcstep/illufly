import pytest
import asyncio
from illufly.base.base_call import BaseCall

class SyncHandler(BaseCall):
    def handle_request(self, value):
        return f"sync: {value}"

class AsyncHandler(BaseCall):
    async def async_handle_request(self, value):
        return f"async: {value}"

class BothHandler(BaseCall):
    def handle_request(self, value):
        return f"sync: {value}"
        
    async def async_handle_request(self, value):
        return f"async: {value}"

class InheritedSyncHandler(SyncHandler):
    pass

class InheritedAsyncHandler(AsyncHandler):
    pass

class NoHandler(BaseCall):
    pass

@pytest.mark.asyncio
async def test_handler_mode_detection():
    """测试处理器模式检测"""
    # 测试同步处理器
    sync_handler = SyncHandler()
    assert sync_handler._get_handler_mode() == 'sync'
    
    # 测试异步处理器
    async_handler = AsyncHandler()
    assert async_handler._get_handler_mode() == 'async'
    
    # 测试双模式处理器
    both_handler = BothHandler()
    assert both_handler._get_handler_mode() == 'both'
    
    # 测试继承的处理器
    inherited_sync = InheritedSyncHandler()
    assert inherited_sync._get_handler_mode() == 'sync'
    
    inherited_async = InheritedAsyncHandler()
    assert inherited_async._get_handler_mode() == 'async'
    
    # 测试未实现处理器的情况
    with pytest.raises(NotImplementedError):
        no_handler = NoHandler()
        no_handler._get_handler_mode()

def test_sync_handler_in_sync_context():
    """测试同步处理器在同步上下文的调用"""
    handler = SyncHandler()
    result = handler("test")
    assert result == "sync: test"

def test_async_handler_in_sync_context():
    """测试异步处理器在同步上下文的调用"""
    handler = AsyncHandler()
    result = handler("test")
    assert result == "async: test"

def test_both_handler_in_sync_context():
    """测试双模式处理器在同步上下文的调用"""
    handler = BothHandler()
    result = handler("test")
    assert result == "sync: test"

@pytest.mark.asyncio
async def test_sync_handler_in_async_context():
    """测试同步处理器在异步上下文的调用"""
    handler = SyncHandler()
    result = await handler("test")
    assert result == "sync: test"

@pytest.mark.asyncio
async def test_async_handler_in_async_context():
    """测试异步处理器在异步上下文的调用"""
    handler = AsyncHandler()
    result = await handler("test")
    assert result == "async: test"

@pytest.mark.asyncio
async def test_both_handler_in_async_context():
    """测试双模式处理器在异步上下文的调用"""
    handler = BothHandler()
    result = await handler("test")
    assert result == "async: test"

def test_sync_context_detection():
    """测试同步上下文检测"""
    handler = SyncHandler()
    assert not handler._is_async_context()

@pytest.mark.asyncio
async def test_async_context_detection():
    """测试异步上下文检测"""
    handler = SyncHandler()
    assert handler._is_async_context() 
