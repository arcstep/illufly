import time
import zmq
import pytest
import logging
import json

logger = logging.getLogger(__name__)

def test_pubsub_basic_behavior():
    """测试ZMQ PUB-SUB的基本行为
    
    验证：
    1. 正常的发布订阅流程
    2. 先发布再订阅无法收到消息
    3. 订阅后才能收到消息
    """
    context = zmq.Context()
    address = "tcp://127.0.0.1:5559"
    
    try:
        # 创建发布者和订阅者
        publisher = context.socket(zmq.PUB)
        subscriber = context.socket(zmq.SUB)
        
        # 绑定和连接
        publisher.bind(address)
        subscriber.connect(address)
        
        # 测试场景1：先发布再订阅
        publisher.send_multipart([
            b"test",
            json.dumps({"msg": "message1"}).encode()
        ])
        time.sleep(0.1)  # 等待消息发送
        
        # 之后再订阅
        subscriber.subscribe(b"test")
        time.sleep(0.1)  # 等待订阅建立
        
        # 尝试接收消息（应该没有消息）
        try:
            subscriber.recv_multipart(flags=zmq.NOBLOCK)
            assert False, "Should not receive message published before subscription"
        except zmq.ZMQError as e:
            assert e.errno == zmq.EAGAIN  # 表示没有消息
            
        # 测试场景2：先订阅再发布
        publisher.send_multipart([
            b"test",
            json.dumps({"msg": "message2"}).encode()
        ])
        time.sleep(0.1)  # 等待消息发送
        
        # 应该能收到消息
        [topic, payload] = subscriber.recv_multipart()
        message = json.loads(payload.decode())
        
        assert topic == b"test"
        assert message["msg"] == "message2"
        
        # 测试场景3：多条消息
        for i in range(3):
            publisher.send_multipart([
                b"test",
                json.dumps({"msg": f"message{i+3}"}).encode()
            ])
            
        time.sleep(0.1)  # 等待消息发送
        
        # 应该能收到所有消息
        for i in range(3):
            [topic, payload] = subscriber.recv_multipart()
            message = json.loads(payload.decode())
            assert topic == b"test"
            assert message["msg"] == f"message{i+3}"
            
    finally:
        # 清理资源
        publisher.close()
        subscriber.close()
        context.term()

def test_pubsub_multiple_topics():
    """测试多主题订阅行为"""
    context = zmq.Context()
    address = "tcp://127.0.0.1:5560"
    
    try:
        publisher = context.socket(zmq.PUB)
        subscriber = context.socket(zmq.SUB)
        
        publisher.bind(address)
        subscriber.connect(address)
        time.sleep(0.1)  # 等待连接建立
        
        # 订阅多个主题
        topics = [b"topic1", b"topic2"]
        for topic in topics:
            subscriber.subscribe(topic)
            
        time.sleep(0.1)  # 等待订阅建立
        
        # 发布到不同主题
        test_messages = {
            "topic1": "message1",
            "topic2": "message2",
            "topic3": "message3"  # 未订阅的主题
        }
        
        for topic, msg in test_messages.items():
            publisher.send_multipart([
                topic.encode(),
                json.dumps({"msg": msg}).encode()
            ])
            
        time.sleep(0.1)  # 等待消息发送
        
        # 应该只收到订阅的主题的消息
        received = []
        for _ in range(2):  # 应该只收到2条消息
            try:
                [topic, payload] = subscriber.recv_multipart(flags=zmq.NOBLOCK)
                message = json.loads(payload.decode())
                received.append((topic.decode(), message["msg"]))
            except zmq.ZMQError as e:
                if e.errno == zmq.EAGAIN:
                    break
                    
        assert len(received) == 2
        assert ("topic1", "message1") in received
        assert ("topic2", "message2") in received
        
    finally:
        publisher.close()
        subscriber.close()
        context.term()
