import pytest
import asyncio
from illufly.base.base_call import BaseCall

class SyncHandler(BaseCall):
    def handle_call(self, value):
        return f"sync: {value}"

class AsyncHandler(BaseCall):
    async def async_handle_call(self, value):
        return f"async: {value}"

class BothHandler(BaseCall):
    def handle_call(self, value):
        return f"sync: {value}"
        
    async def async_handle_call(self, value):
        return f"async: {value}"

class InheritedSyncHandler(SyncHandler):
    pass

class InheritedAsyncHandler(AsyncHandler):
    pass

class NoHandler(BaseCall):
    pass

class ProcessBaseHandler(BaseCall):
    """定义 process 相关的处理方法"""
    def process(self, value):
        raise NotImplementedError
        
    async def async_process(self, value):
        raise NotImplementedError
        
    def do_process(self, *args, **kwargs):
        return self.auto_call(self.process, self.async_process, ProcessBaseHandler)(*args, **kwargs)

class CallBaseHandler(BaseCall):
    """定义 call 相关的处理方法"""
    def handle_call(self, value):
        raise NotImplementedError
        
    async def async_handle_call(self, value):
        raise NotImplementedError
        
    def __call__(self, *args, **kwargs):
        return self.auto_call(self.handle_call, self.async_handle_call, CallBaseHandler)(*args, **kwargs)

class MultiHandler(ProcessBaseHandler, CallBaseHandler):
    """同时继承两个基类，但不实现任何方法"""
    pass

class ImplementedMultiHandler(ProcessBaseHandler, CallBaseHandler):
    """实现所有处理方法"""
    def process(self, value):
        return f"process_sync: {value}"
        
    async def async_process(self, value):
        return f"process_async: {value}"
        
    def handle_call(self, value):
        return f"call_sync: {value}"
        
    async def async_handle_call(self, value):
        return f"call_async: {value}"

class PartialMultiHandler(ProcessBaseHandler, CallBaseHandler):
    """只实现部分方法"""
    def process(self, value):
        return f"process_sync: {value}"
        
    def handle_call(self, value):
        return f"call_sync: {value}"

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

def test_multi_inheritance_sync():
    """测试多重继承场景 - 同步上下文"""
    # 测试未实现任何方法的子类
    multi = MultiHandler()
    with pytest.raises(NotImplementedError):
        multi.do_process("test")
    with pytest.raises(NotImplementedError):
        multi("test")
        
    # 测试实现了所有方法的子类
    impl = ImplementedMultiHandler()
    
    # 测试 process 路径
    assert impl.do_process("test") == "process_sync: test"
    
    # 测试 call 路径
    assert impl("test") == "call_sync: test"
    
    # 测试只实现同步方法的子类
    partial = PartialMultiHandler()
    
    # 测试 process 路径
    assert partial.do_process("test") == "process_sync: test"
    
    # 测试 call 路径
    assert partial("test") == "call_sync: test"

@pytest.mark.asyncio
async def test_multi_inheritance_async():
    """测试多重继承场景 - 异步上下文"""
    # 测试未实现任何方法的子类
    multi = MultiHandler()
    with pytest.raises(NotImplementedError):
        await multi.do_process("test")
    with pytest.raises(NotImplementedError):
        await multi("test")
        
    # 测试实现了所有方法的子类
    impl = ImplementedMultiHandler()
    
    # 测试 process 路径
    assert await impl.do_process("test") == "process_async: test"
    
    # 测试 call 路径
    assert await impl("test") == "call_async: test"
    
    # 测试只实现同步方法的子类
    partial = PartialMultiHandler()
    
    # 测试 process 路径 - 同步方法应该被包装为异步方法
    result = await partial.do_process("test")
    assert result == "process_sync: test"
    
    # 测试 call 路径 - 同步方法应该被包装为异步方法
    result = await partial("test")
    assert result == "call_sync: test" 
