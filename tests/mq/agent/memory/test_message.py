import pytest
from datetime import datetime
from typing import Dict, Any

from illufly.llm.memory.L0_qa.models import Message

class TestMessage:
    """消息测试"""
    
    @pytest.fixture
    def message(self):
        """创建一个基本消息"""
        return Message(role="user", content="你好")
    
    def test_basic_message(self, message):
        """测试基本消息构建"""
        assert message.role == "user"
        assert message.content == "你好"
        assert message.timestamp is not None
        assert isinstance(message.timestamp, datetime)
        
    def test_create_from_str(self):
        """测试从字符串创建消息"""
        msg = Message.create("测试消息")
        assert msg.role == "user"
        assert msg.content == "测试消息"
        
    def test_create_from_tuple(self):
        """测试从元组创建消息"""
        # 测试普通角色
        msg1 = Message.create(("user", "用户消息"))
        assert msg1.role == "user"
        assert msg1.content == "用户消息"
        
        # 测试 ai 到 assistant 的转换
        msg2 = Message.create(("ai", "AI回复"))
        assert msg2.role == "assistant"
        assert msg2.content == "AI回复"
        
        # 测试系统消息
        msg3 = Message.create(("system", "系统提示"))
        assert msg3.role == "system"
        assert msg3.content == "系统提示"
    
    def test_create_from_message_list(self):
        """测试从消息列表创建消息"""
        messages = [
            ("user", "你好"),
            ("ai", "你好！很高兴见到你。")
        ]
        msgs = [Message.create(msg) for msg in messages]
        assert msgs[0].role == "user"
        assert msgs[0].content == "你好"
        assert msgs[1].role == "assistant"
        assert msgs[1].content == "你好！很高兴见到你。"
        
    def test_create_from_dict(self):
        """测试从字典创建消息"""
        # 基本字典
        msg1 = Message.create({
            "role": "user",
            "content": "字典消息"
        })
        assert msg1.role == "user"
        assert msg1.content == "字典消息"
        
        # 带额外字段的字典
        msg2 = Message.create({
            "role": "assistant",
            "content": "回复消息",
            "extra_field": "额外字段"  # 应该被忽略
        })
        assert msg2.role == "assistant"
        assert msg2.content == "回复消息"
        
    def test_create_from_message(self):
        """测试从现有消息创建消息"""
        original = Message(role="user", content="原始消息")
        copied = Message.create(original)
        assert copied.role == original.role
        assert copied.content == original.content
        assert isinstance(copied, Message)
        
    def test_message_property(self):
        """测试 message 属性（用于序列化）"""
        msg = Message(role="user", content="测试消息")
        message_dict = msg.message_dict
        
        # 验证序列化结果
        assert isinstance(message_dict, dict)
        assert message_dict["role"] == "user"
        assert message_dict["content"] == "测试消息"
        assert "timestamp" not in message_dict  # timestamp 应被排除
        
    def test_complex_content(self):
        """测试复杂内容类型"""
        # 字典内容
        content_dict = {
            "text": "带格式的消息",
            "format": "markdown",
            "metadata": {"key": "value"}
        }
        msg = Message.create({
            "role": "assistant",
            "content": content_dict
        })
        assert msg.role == "assistant"
        assert msg.content == content_dict
        assert msg.content["text"] == "带格式的消息"
        
    def test_invalid_role(self):
        """测试无效角色"""
        with pytest.raises(ValueError):
            Message.create(("invalid_role", "消息"))
            
    def test_role_validation(self):
        """测试角色验证"""
        # 有效角色
        valid_roles = ["user", "assistant", "system", "tool"]
        for role in valid_roles:
            msg = Message.create((role, "测试消息"))
            assert msg.role == role
            
        # 无效角色
        invalid_roles = ["admin", "bot", "other"]
        for role in invalid_roles:
            with pytest.raises(ValueError):
                Message.create((role, "测试消息"))