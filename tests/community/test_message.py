import pytest
from datetime import datetime
from typing import Dict, Any

from illufly.community import normalize_messages

class TestMessage:
    """消息测试"""
    
    def test_create_from_str(self):
        """测试从字符串创建消息"""
        msg = normalize_messages("测试消息")[0]
        assert msg['role'] == "user"
        assert msg['content'] == "测试消息"
        
    def test_create_from_tuple(self):
        """测试从元组创建消息"""
        # 测试普通角色
        msg1 = normalize_messages(("user", "用户消息"))[0]
        assert msg1['role'] == "user"
        assert msg1['content'] == "用户消息"
        
        # 测试 ai 到 assistant 的转换
        msg2 = normalize_messages(("ai", "AI回复"))[0]
        assert msg2['role'] == "assistant"
        assert msg2['content'] == "AI回复"
        
        # 测试系统消息
        msg3 = normalize_messages(("system", "系统提示"))[0]
        assert msg3['role'] == "system"
        assert msg3['content'] == "系统提示"
    
    def test_create_from_message_list(self):
        """测试从元组列表创建消息"""
        messages = [
            ("user", "你好"),
            ("ai", "你好！很高兴见到你。")
        ]
        msgs = normalize_messages(messages)
        assert msgs[0]['role'] == "user"
        assert msgs[0]['content'] == "你好"
        assert msgs[1]['role'] == "assistant"
        assert msgs[1]['content'] == "你好！很高兴见到你。"
        
    def test_create_from_dict(self):
        """测试从字典创建消息"""
        # 基本字典
        msg1 = normalize_messages({
            "role": "user",
            "content": "字典消息"
        })[0]
        assert msg1['role'] == "user"
        assert msg1['content'] == "字典消息"
        
        # 带额外字段的字典
        msg2 = normalize_messages({
            "role": "assistant",
            "content": "回复消息",
            "extra_field": "额外字段"  # 应该被忽略
        })[0]
        assert msg2['role'] == "assistant"
        assert msg2['content'] == "回复消息"
        
    def test_complex_content(self):
        """测试复杂内容类型"""
        # 字典内容
        content_dict = {
            "text": "带格式的消息",
            "format": "markdown",
            "metadata": {"key": "value"}
        }
        msg = normalize_messages({
            "role": "assistant",
            "content": content_dict
        })[0]
        assert msg['role'] == "assistant"
        assert msg['content'] == content_dict
        assert msg['content']['text'] == "带格式的消息"
        
    def test_invalid_role(self):
        """测试无效角色"""
        with pytest.raises(ValueError):
            normalize_messages(("invalid_role", "消息"))
            
    def test_role_validation(self):
        """测试角色验证"""
        # 有效角色
        valid_roles = ["user", "assistant", "system", "tool"]
        for role in valid_roles:
            msg = normalize_messages((role, "测试消息"))[0]
            assert msg['role'] == role
            
        # 无效角色
        invalid_roles = ["admin", "bot", "other"]
        for role in invalid_roles:
            with pytest.raises(ValueError):
                normalize_messages((role, "测试消息"))