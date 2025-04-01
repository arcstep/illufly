import pytest
import asyncio
import logging

from illufly.mq.service import ServiceDealer, ServiceRouter, ClientDealer, service_method

@pytest.fixture(scope="module")
def router_address():
    return "tcp://127.0.0.1:5555"

@pytest.fixture()
async def router(router_address):
    """创建并启动路由器"""
    router = ServiceRouter(router_address)
    await router.start()
    await asyncio.sleep(0.1)
    yield router
    # 在停止前等待一小段时间，确保能处理所有关闭请求
    await asyncio.sleep(0.5)
    await router.stop()

class MyMethodTypes(ServiceDealer):
    """测试不同类型的方法处理"""
    
    def __init__(self, router_address: str):
        super().__init__(router_address=router_address)

    # 1. 同步方法
    @service_method(name="sync")
    def sync_method(self, x: int) -> int:
        return x + 1

    # 2. 同步生成器
    @service_method(name="sync_gen")
    def sync_generator(self, start: int, end: int):
        for i in range(start, end):
            yield i

    # 3. 异步方法（协程）
    @service_method(name="async")
    async def async_method(self, x: int) -> int:
        await asyncio.sleep(0.1)
        return x + 1

    # 4. 异步生成器
    @service_method(name="async_gen")
    async def async_generator(self, start: int, end: int):
        for i in range(start, end):
            await asyncio.sleep(0.1)
            yield i

@pytest.mark.asyncio
async def test_method_types(router, router_address):
    """测试不同类型方法的处理"""
    service = MyMethodTypes(router_address)
    await service.start()
    client = ClientDealer(router_address, timeout=2.0)

    try:
        # 1. 测试同步方法        
        async for b in client.stream("sync", 1):
            logging.info(f"stream sync result: {b}")
            assert b == 2
        
        # 2. 测试同步生成器
        numbers = []
        async for num in client.stream("sync_gen", 0, 3):
            logging.info(f"stream sync_gen result: {num}")
            numbers.append(num)
        assert numbers == [0, 1, 2]
        
        # 3. 测试异步方法
        async for b in client.stream("async", 1):
            logging.info(f"stream async result: {b}")
            assert b == 2
        
        # 4. 测试异步生成器
        numbers = []
        async for num in client.stream("async_gen", 0, 3):
            logging.info(f"stream async_gen result: {num}")
            numbers.append(num)
        assert numbers == [0, 1, 2]

    finally:
        await client.close()
        await service.stop() 