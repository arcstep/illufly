import pytest
from illufly.mq.models.enum import BlockType
from illufly.mq.models.models import StreamingBlock, TextChunk, ErrorBlock
from illufly.mq.models.thread import StreamingThread

class TestStreamingThread:
    @pytest.fixture
    def thread(self):
        return StreamingThread(request_id="test_thread")

    def test_add_block(self, thread):
        """测试添加数据块"""
        # 添加一个没有 request_id 的块
        block1 = StreamingBlock.create_block(BlockType.TEXT_CHUNK, text="test", seq=0)
        thread.add_block(block1)
        assert block1.request_id == thread.request_id
        assert len(thread.blocks) == 1

        # 添加一个有匹配 request_id 的块
        block2 = StreamingBlock.create_block(
            BlockType.TEXT_CHUNK, 
            text="test2", 
            seq=1, 
            request_id="test_thread"
        )
        thread.add_block(block2)
        assert len(thread.blocks) == 2

        # 测试添加不匹配的 request_id
        with pytest.raises(ValueError):
            wrong_block = StreamingBlock.create_block(
                BlockType.TEXT_CHUNK,
                text="test3",
                request_id="wrong_thread"
            )
            thread.add_block(wrong_block)

    def test_get_blocks(self, thread):
        """测试获取数据块"""
        # 添加不同类型的块
        text_block = StreamingBlock.create_block(BlockType.TEXT_CHUNK, text="test", seq=0)
        error_block = StreamingBlock.create_block(BlockType.ERROR, error="error")
        thread.add_block(text_block)
        thread.add_block(error_block)

        # 测试获取所有块
        all_blocks = thread.get_blocks()
        assert len(all_blocks) == 2

        # 测试按类型过滤
        text_blocks = thread.get_blocks(BlockType.TEXT_CHUNK)
        assert len(text_blocks) == 1
        assert text_blocks[0].block_type == BlockType.TEXT_CHUNK

    def test_get_last_block(self, thread):
        """测试获取最后一个块"""
        # 空线程
        assert thread.get_last_block() is None

        # 添加块后获取
        block1 = StreamingBlock.create_block(BlockType.TEXT_CHUNK, text="test1", seq=0)
        block2 = StreamingBlock.create_block(BlockType.TEXT_CHUNK, text="test2", seq=1)
        thread.add_block(block1)
        thread.add_block(block2)

        last_block = thread.get_last_block()
        assert last_block == block2

        # 按类型获取最后一个块
        last_text_block = thread.get_last_block(BlockType.TEXT_CHUNK)
        assert last_text_block == block2

    def test_is_completed(self, thread):
        """测试完成状态检查"""
        # 初始状态
        assert not thread.is_completed()

        # 添加非结束块
        text_block = StreamingBlock.create_block(BlockType.TEXT_CHUNK, text="test")
        thread.add_block(text_block)
        assert not thread.is_completed()

        # 添加结束块
        end_block = StreamingBlock.create_block(BlockType.END)
        thread.add_block(end_block)
        assert thread.is_completed() 