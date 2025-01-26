import pytest
from datetime import datetime, timedelta
import tempfile
import shutil
from uuid import uuid4

from illufly.io.rocksdict import IndexedRocksDB
from illufly.llm.conversation.conversation_manager import ConversationManager
from illufly.llm.conversation.L0_dialogue.models import Dialogue, Message
from illufly.llm.conversation.models import ConversationCognitive, FinalCognitive

@pytest.fixture
def db_path():
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path)

@pytest.fixture
async def db(db_path):
    db = IndexedRocksDB(db_path)
    try:
        yield db
    finally:
        db.close()

@pytest.fixture
async def manager(db):
    return ConversationManager(db)

@pytest.fixture
def sample_dialogue():
    """创建示例对话"""
    return Dialogue(
        thread_id="test_thread",
        input_text="你好",
        input_images=[],
        input_files=[],
        output_text="你好！很高兴见到你。",
        messages=[
            Message(
                thread_id="test_thread",
                request_id="req1",
                role="user",
                content="你好"
            ),
            Message(
                thread_id="test_thread",
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

class TestConversationManager:
    """对话管理器测试"""
    
    async def test_create_thread(self, manager):
        """测试创建对话线程"""
        user_id = "test_user"
        thread_id = await manager.create_thread(user_id)
        
        # 验证线程创建
        assert thread_id is not None
        
        # 验证认知状态初始化
        cognitive = await manager.get_conversation_cognitive(thread_id)
        assert cognitive is not None
        assert cognitive.user_id == user_id
        assert cognitive.thread_id == thread_id
        assert len(cognitive.dialogues) == 0
        
    async def test_add_and_get_dialogue(self, manager, sample_dialogue):
        """测试添加和获取对话"""
        # 添加对话
        dialogue_id = await manager.add_dialogue(sample_dialogue)
        
        # 获取对话
        dialogue = await manager.get_dialogue(dialogue_id)
        assert dialogue is not None
        assert dialogue.thread_id == sample_dialogue.thread_id
        assert dialogue.input_text == sample_dialogue.input_text
        assert dialogue.output_text == sample_dialogue.output_text
        
    async def test_get_thread_dialogues(self, manager, sample_dialogue):
        """测试获取线程对话"""
        # 添加多个对话
        await manager.add_dialogue(sample_dialogue)
        
        # 修改时间创建第二个对话
        second_dialogue = sample_dialogue.model_copy()
        second_dialogue.request_time += timedelta(minutes=5)
        second_dialogue.response_time += timedelta(minutes=5)
        await manager.add_dialogue(second_dialogue)
        
        # 获取所有对话
        dialogues = await manager.get_thread_dialogues(sample_dialogue.thread_id)
        assert len(dialogues) == 2
        assert dialogues[0].request_time < dialogues[1].request_time
        
        # 测试时间范围查询
        start_time = sample_dialogue.request_time
        end_time = start_time + timedelta(minutes=3)
        dialogues = await manager.get_thread_dialogues(
            sample_dialogue.thread_id,
            start_time,
            end_time
        )
        assert len(dialogues) == 1
        
    async def test_cognitive_management(self, manager):
        """测试认知状态管理"""
        # 创建线程
        user_id = "test_user"
        thread_id = await manager.create_thread(user_id)
        
        # 获取初始认知状态
        cognitive = await manager.get_conversation_cognitive(thread_id)
        assert cognitive is not None
        
        # 更新认知状态
        cognitive.concepts = [{"id": "1", "name": "测试概念"}]
        await manager.update_conversation_cognitive(cognitive)
        
        # 验证更新
        updated = await manager.get_conversation_cognitive(thread_id)
        assert len(updated.concepts) == 1
        assert updated.concepts[0]["name"] == "测试概念"
        
    async def test_list_user_threads(self, manager, sample_dialogue):
        """测试列出用户线程"""
        # 创建多个线程
        user_id = "test_user"
        thread_id1 = await manager.create_thread(user_id)
        thread_id2 = await manager.create_thread(user_id)
        
        # 添加对话到第一个线程
        dialogue1 = sample_dialogue.model_copy()
        dialogue1.thread_id = thread_id1
        await manager.add_dialogue(dialogue1)
        
        # 添加对话到第二个线程
        dialogue2 = sample_dialogue.model_copy()
        dialogue2.thread_id = thread_id2
        dialogue2.request_time += timedelta(hours=1)
        await manager.add_dialogue(dialogue2)
        
        # 列出所有线程
        threads = await manager.list_user_threads(user_id)
        assert len(threads) == 2
        assert thread_id1 in threads
        assert thread_id2 in threads
        
        # 测试时间范围查询
        start_time = sample_dialogue.request_time
        end_time = start_time + timedelta(minutes=30)
        threads = await manager.list_user_threads(
            user_id,
            start_time,
            end_time
        )
        assert len(threads) == 1
        assert thread_id1 in threads 