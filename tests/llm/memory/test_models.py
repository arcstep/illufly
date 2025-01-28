import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from typing import Dict, List

from illufly.llm.memory.L0_QA.models import Message, QA
from illufly.llm.memory.L1_facts.models import Fact
from illufly.llm.memory.L2_concept.models import Concept
from illufly.llm.memory.L3_thematic_graph.models import ThematicGraph
from illufly.llm.memory.L4_core_view.models import CoreView

class TestL0Models:
    """L0层模型测试"""
    
    def test_message_validation(self):
        """测试消息模型验证"""
        # 正常情况
        message = Message(
            request_id="req1",
            role="user",
            content="测试消息"
        )
        assert message.request_id == "req1"
        assert message.role == "user"
        
        # 测试无效角色
        with pytest.raises(ValueError) as e:
            Message(
                request_id="req1",
                role="invalid_role",
                content="测试消息"
            )
            
        # 测试复杂content
        message = Message(
            request_id="req1",
            role="tool",
            content={"action": "search", "query": "测试查询"}
        )
        assert isinstance(message.content, dict)
        
    def test_dialogue_validation(self):
        """测试对话模型验证"""
        messages = [
            Message(
                request_id="req1",
                role="user",
                content="你好"
            ),
            Message(
                request_id="req1",
                role="assistant",
                content="你好！很高兴见到你。"
            )
        ]
        
        # 正常情况
        QA = QA(
            user_id="test_user",
            thread_id="test_thread",
            input_text="你好",
            input_images=[],
            input_files=[],
            output_text="你好！很高兴见到你。",
            messages=messages,
            summary="简单的问候对话",
            used_time=1.0,
            usage={"prompt_tokens": 10, "completion_tokens": 20}
        )
        assert QA.thread_id == "test_thread"
        assert len(QA.messages) == 2
        
        # 测试时间自动生成
        assert isinstance(QA.request_time, datetime)
        assert isinstance(QA.response_time, datetime)
        
class TestL1Models:
    """L1层模型测试"""
    
    def test_fact_summary_validation(self):
        """测试事实摘要模型验证"""
        now = datetime.now()
        
        # 正常情况
        fact = Fact(
            user_id="test_user",
            thread_id="test_thread",
            title="测试事实",
            content="这是一个测试事实的内容",
            source_chat_threads=["thread1"],
            window_start=now,
            window_end=now + timedelta(hours=1)
        )
        assert fact.title == "测试事实"
        
        # 测试标题长度限制
        with pytest.raises(ValueError) as e:
            Fact(
                user_id="test_user",
                thread_id="test_thread",
                title="这是一个超过三十个字符的非常非常长的标题"*3,
                content="内容",
                source_chat_threads=["thread1"],
                window_start=now,
                window_end=now + timedelta(hours=1)
            )
            
        # 测试内容长度限制
        with pytest.raises(ValueError) as e:
            Fact(
                user_id="test_user",
                thread_id="test_thread",
                title="测试事实",
                content="x" * 201,  # 超过200字符
                source_chat_threads=["thread1"],
                window_start=now,
                window_end=now + timedelta(hours=1)
            )

class TestL2Models:
    """L2层模型测试"""
    
    def test_concept_validation(self):
        """测试概念模型验证"""
        # 正常情况
        concept = Concept(
            user_id="test_user",
            thread_id="test_thread",
            concept_name="测试概念",
            description="这是一个测试概念",
            related_facts=["fact1", "fact2"],
            relations={
                "is_a": ["parent_concept"],
                "has_part": ["child_concept"]
            }
        )
        assert 0 <= concept.confidence <= 1
        assert len(concept.evolution) == 0
        
        # 测试关系更新
        concept.relations["similar_to"] = ["related_concept"]
        assert len(concept.relations) == 3
        
class TestL3Models:
    """L3层模型测试"""
    
    def test_thematic_graph_validation(self):
        """测试主题图模型验证"""
        graph = ThematicGraph(
            user_id="test_user",
            thread_id="test_thread",
            theme_name="测试主题",
            concepts=["concept1", "concept2"],
            summary="测试主题的概念图",
            relations=[
                {
                    "source": "concept1",
                    "target": "concept2",
                    "type": "related_to"
                }
            ]
        )
        assert len(graph.sub_themes) == 0
        assert graph.parent_theme is None
        
        # 测试DOT导出
        dot = graph.to_dot()
        assert "digraph G" in dot
        
    def test_core_view_validation(self):
        """测试核心观点模型验证"""
        view = CoreView(
            user_id="test_user",
            thread_id="test_thread",
            theme_id="theme1",
            statement="这是一个测试观点",
            scope={"domain": "test", "audience": "developer"},
            dependencies=["view1", "view2"],
            valid_until=datetime.now() + timedelta(days=30)
        )
        assert len(view.dependencies) == 2
        assert view.valid_until > datetime.now() 