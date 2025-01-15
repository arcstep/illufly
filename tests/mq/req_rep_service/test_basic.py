import pytest
import asyncio
import time
import logging
from illufly.mq.req_rep_service import ReqRepService

logger = logging.getLogger(__name__)

class AsyncTestService(ReqRepService):
    """测试用的异步服务"""
    async def async_handle_request(self, value):
        await asyncio.sleep(0.1)  # 模拟异步处理
        return f"processed: {value}"

@pytest.fixture
def service():
    """创建测试服务"""
    # 使用随机端口避免冲突
    service = AsyncTestService(logger=logger)
    yield service
    service.cleanup()

def test_service_basic(service):
    """测试基本的异步服务功能"""
    # 发送请求
    request_id = service("test_data")
    
    # 验证请求ID格式
    assert isinstance(request_id, str)
    assert request_id.startswith("REQ_")
    
    # 验证任务已创建
    assert len(service._pending_tasks) > 0
    
    # 验证任务已完成
    time.sleep(0.3)
    assert len(service._pending_tasks) == 0

def test_service_multiple_requests(service):
    """测试多个并发请求"""
    # 发送多个请求
    request_ids = [
        service(f"test_{i}")
        for i in range(3)
    ]
    
    # 验证得到不同的请求ID
    assert len(set(request_ids)) == 3
    # 验证所有任务都被创建
    assert len(service._pending_tasks) == 3
    
    # 验证所有任务都已完成
    time.sleep(0.3)
    assert len(service._pending_tasks) == 0

def test_service_different_input_types(service):
    """测试不同类型的输入"""
    # 测试单个值
    id1 = service("test")
    id2 = service("test", "more")
    id3 = service(value="test")
    
    # 验证所有请求都得到了ID
    assert all(isinstance(id, str) for id in [id1, id2, id3])

    # 验证所有任务都已完成
    time.sleep(0.3)
    assert len(service._pending_tasks) == 0
