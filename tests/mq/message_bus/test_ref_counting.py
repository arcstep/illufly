import pytest
import logging
import os
from illufly.mq.message_bus import MessageBus, BindState
from urllib.parse import urlparse
from unittest.mock import patch, MagicMock
import zmq

logger = logging.getLogger(__name__)

class TestMessageBusRefCounting:
    """消息总线引用计数测试
    
    设计意图：
    1. 验证引用计数的正确性
    2. 确保资源正确清理
    3. 测试多实例场景
    4. 验证不同通信模式下的行为
    """
    
    @pytest.mark.parametrize("address", [
        "inproc://test_refs",
        pytest.param(
            "ipc:///tmp/test_refs.ipc",
            marks=pytest.mark.skipif(
                os.name == 'nt',
                reason="IPC not supported on Windows"
            )
        ),
        "tcp://127.0.0.1:5557",
        pytest.param(
            "tcp://example.com:5557",
            marks=pytest.mark.remote
        )
    ])
    def test_ref_counting_basic(self, address):
        """测试基本的引用计数功能"""
        if "example.com" in address:
            # 创建一个模拟的 socket 对象
            mock_socket = MagicMock()
            mock_socket.bind = MagicMock()  # 模拟 bind 方法
            
            # 模拟 zmq.Context().socket() 返回我们的模拟 socket
            with patch.object(zmq.Context, 'socket', return_value=mock_socket):
                bus1 = MessageBus(address=address, logger=logger)
                assert MessageBus._bound_refs == 0, "远程绑定不应计数"
                assert MessageBus._bound_state == BindState.REMOTE_BOUND
                bus1.cleanup()
        else:
            bus1 = MessageBus(address=address, logger=logger)
            parsed = urlparse(address)
            is_local = parsed.scheme == 'inproc' or (
                parsed.scheme in ('tcp', 'ipc') and 
                parsed.hostname in ('localhost', '127.0.0.1', None)
            )
            
            if is_local:
                assert MessageBus._bound_refs == 1, "本地绑定应该有1个引用"
                assert MessageBus._bound_state == BindState.LOCAL_BOUND
            
            bus1.cleanup()
            assert MessageBus._bound_refs == 0, "清理后引用计数应为0"

    def test_ref_counting_error_cases(self):
        """测试引用计数的错误处理"""
        bus = MessageBus(logger=logger)
        
        # 重复清理同一个实例
        bus.cleanup()
        bus.cleanup()  # 不应导致负数引用计数
        assert MessageBus._bound_refs >= 0, "引用计数不应为负"
        
        # 创建新实例时应正确初始化
        new_bus = MessageBus(logger=logger)
        assert MessageBus._bound_refs == 1, "新实例应重置引用计数为1"
        new_bus.cleanup()

    @pytest.mark.parametrize("num_instances", [2, 5, 10])
    def test_multiple_local_instances(self, num_instances):
        """测试多个本地实例的引用计数"""
        buses = []
        try:
            # 创建多个实例
            for i in range(num_instances):
                bus = MessageBus(address="inproc://test_refs", logger=logger)
                buses.append(bus)
                assert MessageBus._bound_refs == i + 1, \
                    f"创建第{i+1}个实例后，引用计数应为{i+1}"
            
            # 逐个清理
            for i, bus in enumerate(reversed(buses)):
                bus.cleanup()
                expected_refs = num_instances - i - 1
                assert MessageBus._bound_refs == expected_refs, \
                    f"清理第{i+1}个实例后，应剩余{expected_refs}个引用"
                
        finally:
            for bus in buses:
                bus.cleanup()

    def test_mixed_binding_scenarios(self):
        """测试混合绑定场景"""
        # 创建一个模拟的 socket 对象
        mock_socket = MagicMock()
        mock_socket.bind = MagicMock()  # 模拟 bind 方法
        
        # 模拟远程绑定
        with patch.object(zmq.Context, 'socket', return_value=mock_socket):
            remote_bus = MessageBus(address="tcp://example.com:5557", logger=logger)
            assert MessageBus._bound_state == BindState.REMOTE_BOUND
            assert MessageBus._bound_refs == 0
            
            # 本地绑定不需要mock
            local_bus = MessageBus(address="inproc://test_refs", logger=logger)
            assert MessageBus._bound_state == BindState.LOCAL_BOUND
            assert MessageBus._bound_refs == 1
            
            # 清理
            remote_bus.cleanup()
            assert MessageBus._bound_state == BindState.LOCAL_BOUND
            assert MessageBus._bound_refs == 1
            
            local_bus.cleanup()
            assert MessageBus._bound_state == BindState.UNBOUND
            assert MessageBus._bound_refs == 0

    def test_concurrent_access(self):
        """测试并发访问时的引用计数"""
        import threading
        import random
        import time
        
        def worker():
            """模拟随机的创建和清理操作"""
            buses = []
            try:
                for _ in range(random.randint(1, 5)):
                    bus = MessageBus(logger=logger)
                    buses.append(bus)
                    time.sleep(random.random() * 0.1)  # 随机延迟
                
                for bus in buses:
                    bus.cleanup()
                    time.sleep(random.random() * 0.1)  # 随机延迟
                    
            except Exception as e:
                logger.error(f"Worker error: {e}")
                raise
        
        threads = []
        for _ in range(5):  # 创建5个并发线程
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()
        
        # 等待所有线程完成
        for t in threads:
            t.join()
        
        # 验证最终状态
        assert MessageBus._bound_refs == 0, "所有线程完成后引用计数应为0"
        assert MessageBus._bound_socket is None, "所有线程完成后socket应为None" 