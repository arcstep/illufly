import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from typing import Dict, List

from illufly.agent.memory.L0_qa.models import HistoryMessage, QA, Thread
from illufly.agent.memory.L1_facts.models import Fact
from illufly.agent.memory.L2_concept.models import Concept
from illufly.agent.memory.L3_thematic_graph.models import ThematicGraph
from illufly.agent.memory.L4_core_view.models import CoreView

class Test_thread_Models:
    """Thread模型测试"""

    def test_thread_validation(self):
        """测试Thread模型验证"""
        thread = Thread(user_id="test_user")
        assert thread.user_id == "test_user"
        assert thread.thread_id is not None

class Test_L0_Models:
    """L0层模型测试"""
    
    def test_message_validation(self):
        """测试消息模型验证"""
        # 正常情况
        message = HistoryMessage(
            role="user",
            content="测试消息"
        )
        assert message.role == "user"
        
        # 测试无效角色
        with pytest.raises(ValueError) as e:
            HistoryMessage(
                role="invalid_role",
                content="测试消息"
            )
            
        # 测试复杂content
        message = HistoryMessage(
            role="tool",
            content={"action": "search", "query": "测试查询"}
        )
        assert isinstance(message.content, dict)
        
    def test_qa_validation(self):
        """测试对话模型验证"""
        messages = [
            HistoryMessage(
                role="user",
                content="你好"
            ),
            HistoryMessage(
                role="assistant",
                content="你好！很高兴见到你。"
            )
        ]
        
        # 正常情况
        qa = QA(
            qa_id="test_qa_id",
            user_id="test_user",
            thread_id="test_thread",
            messages=messages,
            summary=messages,
            used_time=1.0,
            usage={"prompt_tokens": 10, "completion_tokens": 20}
        )
        assert qa.thread_id == "test_thread"
        assert len(qa.messages) == 2
        
        # 测试时间自动生成
        assert isinstance(qa.request_time, datetime)
        assert isinstance(qa.response_time, datetime)

    def test_qa_with_simple_messages(self):
        """测试对话模型验证"""
        # 正常情况
        qa = QA(
            qa_id="test_qa_id",
            user_id="test_user",
            thread_id="test_thread",
            messages=[
                ("user", "你好"),
                ("ai", "你好！很高兴见到你。"),
                ("user", "你叫什么名字？"),
                ("ai", "我叫小明。")
            ],
            summary=[
                HistoryMessage(role="user", content="你叫什么名字？"),
                HistoryMessage(role="assistant", content="我叫小明。")
            ]
        )
        assert qa.thread_id == "test_thread"
        assert len(qa.messages) == 4
        
        # 测试时间自动生成
        assert isinstance(qa.request_time, datetime)
        assert isinstance(qa.response_time, datetime)

class Test_L1_Models:
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

class Test_L2_Models:
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
        
class Test_L3_Models:
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

class Test_L4_Models:
    """L4层模型测试"""
    
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