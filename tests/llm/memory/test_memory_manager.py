import pytest
import tempfile
import shutil
import logging
import uuid

from enum import Enum
from typing import Dict, List
from datetime import datetime, timedelta

from illufly.io.rocksdict import IndexedRocksDB
from illufly.llm.memory.memory_manager import MemoryManager
from illufly.llm.memory.models import ConversationCognitive, FinalCognitive
from illufly.llm.memory.L0_dialogue.models import Dialogue, Message
from illufly.llm.memory.L1_facts.models import Fact
from illufly.llm.memory.L2_concept.models import Concept
from illufly.llm.memory.L3_thematic_graph.models import ThematicGraph
from illufly.llm.memory.L4_core_view.models import CoreView

logger = logging.getLogger(__name__)

@pytest.fixture
def db_path():
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path)

@pytest.fixture
def db(db_path):
    db = IndexedRocksDB(db_path)
    try:
        yield db
    finally:
        db.close()

@pytest.fixture
def user_id():
    return "test_user"

@pytest.fixture
def thread_id():
    return "test_thread"

@pytest.fixture
def manager(db, user_id, thread_id):
    return MemoryManager(db, user_id, thread_id)

@pytest.fixture
def sample_dialogue():
    """创建示例对话"""
    return Dialogue(
        user_id=user_id,
        thread_id=thread_id,
        input_text="你好",
        input_images=[],
        input_files=[],
        output_text="你好！很高兴见到你。",
        messages=[
            Message(
                user_id=user_id,
                thread_id=thread_id,
                request_id="req1",
                role="user",
                content="你好"
            ),
            Message(
                user_id=user_id,
                thread_id=thread_id,
                request_id="req1",
                role="assistant",
                content="你好！很高兴见到你。"
            )
        ],
        summary="简单的问候对话",
        request_time=datetime.now(),
        response_time=datetime.now() + timedelta(seconds=1),
        used_time=1.0,
        usage={"prompt_tokens": 10, "completion_tokens": 20}
    )

class TestMemoryManager:
    """对话管理器测试"""
    
    def test_create_thread(self, manager):
        """测试创建对话线程"""
        user_id = "test_user"
        thread_id = manager.create_thread(user_id)
        
        # 验证线程创建
        assert thread_id is not None
        
        # 验证认知状态初始化
        cognitive = manager.get_conversation_cognitive(thread_id)
        assert cognitive is not None
        assert cognitive.user_id == user_id
        assert cognitive.thread_id == thread_id
        assert len(cognitive.dialogues) == 0
        
    def test_add_and_get_dialogue(self, manager, sample_dialogue):
        """测试添加和获取对话"""
        # 添加对话
        dialogue_id = manager.add_dialogue(sample_dialogue)
        
        # 获取对话
        dialogue = manager.get_dialogue(dialogue_id)
        assert dialogue is not None
        assert dialogue.thread_id == sample_dialogue.thread_id
        assert dialogue.input_text == sample_dialogue.input_text
        assert dialogue.output_text == sample_dialogue.output_text
        
    def test_get_thread_dialogues(self, manager, sample_dialogue):
        """测试获取线程对话"""
        # 添加多个对话
        manager.add_dialogue(sample_dialogue)
        
        # 修改时间创建第二个对话
        second_dialogue = sample_dialogue.model_copy()
        second_dialogue.dialogue_id = "test_dialogue.2"
        second_dialogue.request_time += timedelta(minutes=5)
        second_dialogue.response_time += timedelta(minutes=5)
        manager.add_dialogue(second_dialogue)
        
        # 获取所有对话
        dialogues = manager.get_thread_dialogues(sample_dialogue.thread_id)
        assert len(dialogues) == 2
        assert dialogues[0].request_time < dialogues[1].request_time
        
        # 测试时间范围查询
        start_time = sample_dialogue.request_time
        end_time = start_time + timedelta(minutes=3)
        dialogues = manager.get_thread_dialogues(
            sample_dialogue.thread_id,
            start_time,
            end_time
        )
        assert len(dialogues) == 1
        
    def test_cognitive_management(self, manager):
        """测试认知状态管理"""
        # 创建线程
        user_id = "test_user"
        thread_id = manager.create_thread(user_id)
        
        # 获取初始认知状态
        cognitive = manager.get_conversation_cognitive(thread_id)
        assert cognitive is not None
        
        # 更新认知状态 - 使用完整的概念对象
        concept = Concept(
            concept_id="1",
            concept_name="测试概念",
            description="这是一个测试概念"
        )
        cognitive.concepts = [concept]
        manager.update_conversation_cognitive(cognitive)
        
        # 验证更新
        updated = manager.get_conversation_cognitive(thread_id)
        assert len(updated.concepts) == 1
        assert updated.concepts[0].concept_name == "测试概念"
        
    def test_list_user_threads(self, manager, sample_dialogue):
        """测试列出用户线程"""
        # 创建多个线程
        user_id = "test_user"
        thread_id1 = manager.create_thread(user_id)
        thread_id2 = manager.create_thread(user_id)
        
        # 添加对话到第一个线程
        dialogue1 = sample_dialogue.model_copy()
        dialogue1.thread_id = thread_id1
        dialogue1.dialogue_id = "test_dialogue.2"
        manager.add_dialogue(dialogue1)
        
        # 添加对话到第二个线程
        dialogue2 = sample_dialogue.model_copy()
        dialogue2.thread_id = thread_id2
        dialogue2.request_time += timedelta(hours=1)
        manager.add_dialogue(dialogue2)
        
        # 列出所有线程
        threads = manager.list_user_threads(user_id)
        assert len(threads) == 2
        assert thread_id1 in threads
        assert thread_id2 in threads
        
        # 测试时间范围查询
        start_time = sample_dialogue.request_time
        end_time = start_time + timedelta(minutes=30)
        threads = manager.list_user_threads(
            user_id,
            start_time,
            end_time
        )
        assert len(threads) == 1
        assert thread_id1 in threads 

    def test_continuse_chat(self, manager):
        """测试连续对话"""
        user_id = "test_user"
        thread_id = manager.create_thread(user_id)

        dummy_input = "你好"
        dummy_output = "你好！很高兴见到你。"
        def create_dummy_dialogue(input_text, output_text):
            message_list = [
                Message(
                    thread_id=thread_id,
                    request_id="req1",
                    role="user",
                    content=input_text
                ),
                Message(
                    thread_id=thread_id,
                    request_id="req1",
                    role="assistant",
                    content=output_text
                )
            ]
            return Dialogue(
                dialogue_id=str(uuid.uuid4()),
                thread_id=thread_id,
                input_text=input_text,
                output_text=output_text,
                messages=message_list,
                summary="简单的问候对话"
            )

        # 添加对话并立即验证
        for i in range(5):
            dialogue = create_dummy_dialogue(dummy_input, dummy_output)
            dialogue_id = manager.add_dialogue(dialogue)
            logger.info(f"添加对话: {dialogue_id}")
            # 立即验证单条对话
            saved_dialogue = manager.get_dialogue(dialogue_id)
            logger.info(f"获取对话: {saved_dialogue}")
            assert saved_dialogue is not None
            
            # 验证认知状态
            cognitive = manager.get_conversation_cognitive(thread_id)
            logger.info(f"当前对话数量: {len(cognitive.dialogues)}")  # 添加调试信息
            
        # 最终验证
        cognitive = manager.get_conversation_cognitive(thread_id)
        assert len(cognitive.dialogues) == 5
