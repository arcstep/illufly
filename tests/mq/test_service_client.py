import pytest
import asyncio
import logging
from typing import Dict, Any, AsyncGenerator
from illufly.mq.base import MQBus
from illufly.mq.types import ServiceMode
from illufly.mq.service import BaseService
from illufly.mq.client import MQClient
from illufly.mq.registry import RegistryClient
import random
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@pytest.fixture
async def mq_bus(caplog):
    """创建MQ总线实例"""
    caplog.set_level(logging.INFO)
    bus = MQBus(mode=MQBus.MODE_INPROC, logger=logger)
    bus.start()
    try:
        yield bus
    finally:
        bus.stop()

@pytest.fixture
async def registry_client(mq_bus):
    """创建注册中心客户端"""
    client = RegistryClient(logger=logger)
    await client.verify_connection()
    try:
        yield client
    finally:
        await client.close()

@pytest.fixture
async def mq_client(registry_client):
    """创建 MQ 客户端"""
    client = MQClient(registry_client)
    try:
        yield client
    finally:
        await client.close()

# 测试服务实现
class CalcService(BaseService):
    """计算服务 - 请求响应模式"""
    def __init__(self, name: str, registry_client: RegistryClient):
        super().__init__(name, registry_client, ServiceMode.REQUEST_REPLY)
        
    async def get_methods(self) -> Dict[str, str]:
        return {
            "add": "加法运算",
            "subtract": "减法运算"
        }
        
    async def process_request(self, request: Dict) -> Any:
        method = request["method"]
        params = request["params"]
        
        if method == "add":
            return params["a"] + params["b"]
        elif method == "subtract":
            return params["a"] - params["b"]
        raise ValueError(f"未知的方法: {method}")

class DataPipelineService(BaseService):
    """数据管道服务 - 管道模式"""
    def __init__(self, name: str, registry_client: RegistryClient):
        super().__init__(name, registry_client, ServiceMode.PIPELINE)
        
    async def get_methods(self) -> Dict[str, str]:
        return {
            "process": "数据处理"
        }
                
    async def process_pipeline(self, data: Dict) -> Dict:
        """处理管道数据"""
        return {
            "processed": data["value"] * 2,
            "timestamp": time.time()
        }

class MetricsService(BaseService):
    """指标服务 - 发布订阅模式"""
    def __init__(self, name: str, registry_client: RegistryClient):
        super().__init__(name, registry_client, ServiceMode.PUB_SUB)
        
    async def generate_publication(self) -> AsyncGenerator[tuple, None]:
        """实际使用的方法"""
        while True:
            yield "metrics", {
                "cpu": random.random() * 100,
                "memory": random.random() * 100,
                "timestamp": time.time()
            }

class LogCollector(BaseService):
    """日志收集器 - 推拉模式"""
    def __init__(self, name: str, registry_client: RegistryClient):
        super().__init__(name, registry_client, ServiceMode.PUSH_PULL)
        
    async def get_methods(self) -> Dict[str, str]:
        return {
            "collect": "收集日志"
        }
        
    async def process_request(self, request: Dict) -> None:
        # 推拉模式不需要返回值
        logger.info(f"收到日志: {request}")

class StreamProcessService(BaseService):
    """流处理服务 - 路由模式"""
    def __init__(self, name: str, registry_client: RegistryClient):
        super().__init__(name, registry_client, ServiceMode.ROUTER)
        
    async def get_methods(self) -> Dict[str, str]:
        return {
            "process_stream": "流数据处理",
            "generate_stream": "生成流数据"
        }
        
    async def process_request(self, request: Dict) -> Any:
        method = request["method"]
        params = request["params"]
        
        if method == "generate_stream":
            # 直接返回数据列表
            count = params.get("count", 3)
            for i in range(count):
                yield {"value": i}
            
        elif method == "process_stream":
            # 处理输入流
            data = params["data"]
            for item in data:
                yield {
                    "processed": item * 2,
                    "timestamp": time.time()
                }

class DataStreamPipeline(BaseService):
    """数据流水线服务 - 管道模式"""
    def __init__(self, name: str, registry_client: RegistryClient):
        super().__init__(name, registry_client, ServiceMode.PIPELINE)
        
    async def get_methods(self) -> Dict[str, str]:
        return {
            "stream_process": "流水线处理"
        }
        
    async def process_pipeline(self, data: Dict) -> Dict:
        # 流水线处理
        value = data.get("value", 0)
        await asyncio.sleep(0.1)  # 模拟处理时间
        return {
            "stage": self.name,
            "value": value + 1,
            "timestamp": time.time()
        }

class StreamService(BaseService):
    """流式服务 - 路由模式"""
    def __init__(self, name: str, registry_client: RegistryClient):
        super().__init__(name, registry_client, ServiceMode.ROUTER)
        
    async def get_methods(self) -> Dict[str, str]:
        return {
            "generate": "生成流数据",
            "process": "处理流数据"
        }
        
    async def process_request(self, request: Dict) -> Any:
        method = request["method"]
        params = request.get("params", {})
        
        # 所有方法都使用 yield 返回数据
        if method == "generate":
            count = params.get("count", 3)
            for i in range(count):
                yield {
                    "value": i,
                    "timestamp": time.time()
                }
                
        elif method == "process":
            data = params.get("data", [])
            for item in data:
                yield {
                    "processed": item * 2,
                    "timestamp": time.time()
                }
                
        else:
            raise ValueError(f"未知的方法: {method}")

# 测试夹具
@pytest.fixture
async def calc_service(registry_client):
    """创建计算服务"""
    service = CalcService("calc_service", registry_client)
    await service.start()
    try:
        yield service
    finally:
        await service.stop()

@pytest.fixture
async def pipeline_service(registry_client):
    """创建管道服务"""
    service = DataPipelineService("data_pipeline", registry_client)
    await service.start()
    yield service
    await service.stop()

@pytest.fixture
async def metrics_service(registry_client):
    """创建指标服务"""
    service = MetricsService("metrics_service", registry_client)
    await service.start()
    try:
        yield service
    finally:
        await service.stop()

@pytest.fixture
async def log_collector(registry_client):
    """创建日志收集器"""
    service = LogCollector("log_collector", registry_client)
    await service.start()
    try:
        yield service
    finally:
        await service.stop()

@pytest.fixture
async def stream_service(registry_client):
    """创建流式服务"""
    service = StreamService("stream_service", registry_client)
    await service.start()
    yield service
    await service.stop()

@pytest.fixture
async def stream_pipeline(registry_client):
    """创建流水线服务"""
    service = DataStreamPipeline("stream_pipeline", registry_client)
    await service.start()
    try:
        yield service
    finally:
        await service.stop()

# 测试用例
@pytest.mark.asyncio
async def test_request_reply(mq_client, calc_service):
    """测试请求响应模式"""
    result = await mq_client.call("calc_service", "add", {"a": 1, "b": 2})
    assert result == 3

@pytest.mark.asyncio
async def test_push_pull(mq_client, log_collector):
    """测试推拉模式"""
    await mq_client.push("log_collector", {
        "level": "info",
        "message": "test log"
    })
    # 无需断言，因为是单向推送

@pytest.mark.asyncio
async def test_pipeline(mq_client, pipeline_service):
    """测试管道模式"""
    result = await mq_client.pipeline("data_pipeline", {
        "value": 21
    })
    assert result["processed"] == 42
    assert "timestamp" in result

@pytest.mark.asyncio
async def test_pub_sub(mq_client, metrics_service):
    """测试发布订阅模式"""
    results = []
    async def collect_metrics():
        async for msg in mq_client.subscribe("metrics_service", "metrics"):
            results.append(msg)
            if len(results) >= 3:
                break
                
    # 限时运行收集任务
    try:
        await asyncio.wait_for(collect_metrics(), timeout=5.0)
    except asyncio.TimeoutError:
        pass
        
    assert len(results) == 3
    for result in results:
        assert "cpu" in result
        assert "memory" in result
        assert "timestamp" in result

@pytest.mark.asyncio
async def test_router(mq_client, stream_service):
    """测试路由模式"""
    results = []
    # 先获取迭代器
    response_iterator = await mq_client.call("stream_service", "generate", {"count": 3})
    # 然后迭代
    async for data in response_iterator:
        results.append(data)
        
    assert len(results) == 3
    for i, result in enumerate(results):
        assert result["value"] == i

@pytest.mark.asyncio
async def test_router_stream(mq_client, stream_service):
    """测试路由模式的流式处理"""
    results = []
    response_iterator = await mq_client.call("stream_service", "generate", {"count": 3})
    async for data in response_iterator:
        results.append(data)
        
    assert len(results) == 3
    for i, result in enumerate(results):
        assert result["value"] == i
        assert "timestamp" in result

@pytest.mark.asyncio
async def test_pipeline_stream(mq_client, stream_pipeline):
    """测试管道模式的流处理"""
    # 发送多个数据到管道
    input_values = [1, 2, 3]
    results = []
    
    for value in input_values:
        # 发送数据
        await mq_client.call(
            "stream_pipeline", 
            "stream_process", 
            {"value": value}
        )
        
        # 获取处理结果
        result = await mq_client.call("stream_pipeline", "stream_process")
        results.append(result)
    
    assert len(results) == 3
    for i, result in enumerate(results):
        assert result["value"] == input_values[i] + 1
        assert "timestamp" in result

@pytest.mark.asyncio
async def test_combined_stream_processing(
    mq_client, 
    stream_service, 
    stream_pipeline, 
    metrics_service
):
    """测试组合流处理"""
    # 收集指标
    metrics = []
    metrics_task = asyncio.create_task(
        collect_metrics(mq_client, metrics, count=2)
    )
    
    # 同时处理数据流
    stream_results = []
    stream_task = asyncio.create_task(
        process_stream(mq_client, stream_results, count=2)
    )
    
    # 等待所有任务完成
    await asyncio.gather(metrics_task, stream_task)
    
    assert len(metrics) == 2
    assert len(stream_results) == 2

# 辅助函数
async def collect_metrics(client, results, count):
    async for metric in client.call("metrics_service", "metrics"):
        results.append(metric)
        if len(results) >= count:
            break

async def process_stream(client, results, count):
    async for data in client.call(
        "stream_service", 
        "generate_stream", 
        {"count": count}
    ):
        results.append(data) 