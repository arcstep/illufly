import pytest
import asyncio
import threading
import time
import logging
from illufly.base.async_service import AsyncService

class TestAsyncService:
    """测试AsyncService在各种环境下的行为"""
    
    def setup_method(self):
        self.logger = logging.getLogger(__name__)
        self.service = AsyncService(self.logger)
        
    async def dummy_task(self, duration=0.1):
        """测试用的异步任务"""
        await asyncio.sleep(duration)
        return "done"
        
    async def dummy_generator(self, count=3):
        """测试用的异步生成器"""
        for i in range(count):
            await asyncio.sleep(0.1)
            yield i
            
    def test_sync_environment(self):
        """测试在同步环境中运行"""
        # 使用装饰器转换异步函数
        @self.service.to_sync
        async def async_func():
            return await self.dummy_task()
            
        result = async_func()
        assert result == "done"
        
    def test_nested_event_loop(self):
        """测试在嵌套事件循环环境中运行"""
        def create_running_loop():
            """创建一个在后台运行的事件循环"""
            loop = asyncio.new_event_loop()
            
            def run_loop():
                asyncio.set_event_loop(loop)
                loop.run_forever()
                
            thread = threading.Thread(target=run_loop, daemon=True)
            thread.start()
            time.sleep(0.1)  # 等待循环启动
            return loop, thread
            
        # 创建后台事件循环
        background_loop, thread = create_running_loop()
        
        try:
            # 在嵌套环境中运行异步代码
            @self.service.to_sync
            async def nested_async():
                return await self.dummy_task()
                
            result = nested_async()
            assert result == "done"
            
        finally:
            # 清理后台事件循环
            background_loop.call_soon_threadsafe(background_loop.stop)
            thread.join(timeout=1)
            background_loop.close()
            
    @pytest.mark.asyncio
    async def test_async_environment(self):
        """测试在异步环境中运行"""
        async with self.service.managed_async():
            result = await self.dummy_task()
            assert result == "done"
            
    def test_generator_conversion(self):
        """测试生成器转换"""
        # 将异步生成器转换为同步生成器
        gen = self.service.wrap_async_generator(self.dummy_generator())
        results = list(gen)
        assert results == [0, 1, 2]
        
    def test_concurrent_tasks(self):
        """测试并发任务管理"""
        async def run_concurrent():
            tasks = []
            for i in range(3):
                task = asyncio.create_task(self.dummy_task())
                self.service._track_task(task)
                tasks.append(task)
            
            results = await asyncio.gather(*tasks)
            assert all(r == "done" for r in results)
            
            # 验证任务已被清理
            await self.service._cleanup_tasks()
            assert len(self.service._tasks) == 0
            
        with self.service.managed_sync():
            asyncio.get_event_loop().run_until_complete(run_concurrent())
            
    def test_task_cleanup(self):
        """测试任务清理机制"""
        cleanup_done = asyncio.Event()
        
        async def long_running_task():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cleanup_done.set()
                raise  # 重要：重新抛出 CancelledError
                
        async def run_with_cleanup():
            task = asyncio.create_task(long_running_task())
            self.service._track_task(task)
            await asyncio.sleep(0.1)
            await self.service._cleanup_tasks()
            
            # 等待任务实际被取消
            try:
                await asyncio.wait_for(cleanup_done.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                raise AssertionError("Task was not cancelled in time")
                
            assert len(self.service._tasks) == 0
            assert task.cancelled()
            
        with self.service.managed_sync():
            asyncio.get_event_loop().run_until_complete(run_with_cleanup()) 