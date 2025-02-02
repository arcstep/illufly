import pytest
import asyncio
from illufly.mq.service import ServiceDealer

@pytest.fixture(scope="module")
def router_address():
    return "tcp://127.0.0.1:5555"

class MyMethodTypes(ServiceDealer):
    """测试不同类型的方法处理"""
    
    def __init__(self, router_address: str):
        super().__init__(router_address=router_address, service_id="test_service")

    # 1. 同步方法
    @ServiceDealer.service_method(name="sync")
    def sync_method(self, x: int) -> int:
        return x + 1

    # 2. 同步生成器
    @ServiceDealer.service_method(name="sync_gen")
    def sync_generator(self, start: int, end: int):
        for i in range(start, end):
            yield i

    # 3. 异步方法（协程）
    @ServiceDealer.service_method(name="async")
    async def async_method(self, x: int) -> int:
        await asyncio.sleep(0.1)
        return x + 1

    # 4. 异步生成器
    @ServiceDealer.service_method(name="async_gen")
    async def async_generator(self, start: int, end: int):
        for i in range(start, end):
            await asyncio.sleep(0.1)
            yield i

@pytest.mark.asyncio
async def test_method_types(router_address):
    """测试不同类型方法的处理"""
    service = MyMethodTypes(router_address)
    await service.start()

    try:
        # 1. 测试同步方法
        result = await service.sync_method(1)
        assert result == 2
        
        # 2. 测试同步生成器
        numbers = []
        async for num in service.sync_generator(0, 3):
            numbers.append(num)
        assert numbers == [0, 1, 2]
        
        # 3. 测试异步方法
        result = await service.async_method(1)
        assert result == 2
        
        # 4. 测试异步生成器
        numbers = []
        async for num in service.async_generator(0, 3):
            numbers.append(num)
        assert numbers == [0, 1, 2]

    finally:
        await service.stop() 