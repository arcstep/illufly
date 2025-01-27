import pytest
from datetime import datetime, timedelta

from illufly.llm.memory.L0_dialogue.models import Dialogue, Message
from illufly.llm.memory.L0_dialogue.dialogue_manager import DialogueManager

class TestDialogue:
    """对话测试"""
    
    @pytest.fixture
    def sample_dialogue(self, user_id, thread_id):
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
                    role="user",
                    content="你好"
                ),
                Message(
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

    def test_dialogue_creation(self, sample_dialogue, user_id, db):
        """测试对话创建"""
        assert sample_dialogue.dialogue_id is not None

        manager = DialogueManager(db, user_id=user_id)
        manager.create_thread(title="测试对话", description="测试对话", thread_id=sample_dialogue.thread_id)
        manager.add_dialogue(sample_dialogue)

        # 验证对话是否成功添加
        all_threads = manager.all_threads()
        assert sample_dialogue.thread_id in [thread.thread_id for thread in all_threads]
