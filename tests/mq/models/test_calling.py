import pytest
from illufly.mq.models.enum import BlockType
from illufly.mq.models.models import StreamingBlock
from illufly.mq.models.thread import StreamingThread
from illufly.mq.models.calling import StreamingCalling

class TestStreamingCalling:
    @pytest.fixture
    def calling(self):
        return StreamingCalling(calling_id="test_calling")

    def test_add_thread(self, calling):
        """测试添加线程"""
        thread = StreamingThread(request_id="test_thread")
        calling.add_thread(thread)
        assert len(calling.threads) == 1

        # 测试添加重复线程
        with pytest.raises(ValueError):
            calling.add_thread(thread)

    def test_get_or_create_thread(self, calling):
        """测试获取或创建线程"""
        # 获取新线程
        thread1 = calling.get_or_create_thread("thread1")
        assert thread1.request_id == "thread1"
        assert len(calling.threads) == 1

        # 获取已存在的线程
        thread2 = calling.get_or_create_thread("thread1")
        assert thread2 == thread1
        assert len(calling.threads) == 1

    def test_add_block(self, calling):
        """测试添加数据块"""
        # 测试没有 request_id 的情况
        with pytest.raises(ValueError):
            block = StreamingBlock.create_block(BlockType.TEXT_CHUNK, text="test")
            calling.add_block(block)

        # 测试正常添加
        block = StreamingBlock.create_block(
            BlockType.TEXT_CHUNK,
            text="test",
            request_id="thread1"
        )
        calling.add_block(block)
        assert len(calling.threads) == 1
        assert len(calling.get_blocks("thread1")) == 1

    def test_get_thread(self, calling):
        """测试获取线程"""
        # 获取不存在的线程
        assert calling.get_thread("nonexistent") is None

        # 获取存在的线程
        thread = StreamingThread(request_id="test_thread")
        calling.add_thread(thread)
        assert calling.get_thread("test_thread") == thread

    def test_get_threads(self, calling):
        """测试获取线程列表"""
        # 添加测试线程
        thread1 = StreamingThread(request_id="thread1")
        thread2 = StreamingThread(request_id="thread2")
        calling.add_thread(thread1)
        calling.add_thread(thread2)

        # 添加结束块到 thread1
        end_block = StreamingBlock.create_block(BlockType.END)
        thread1.add_block(end_block)

        # 测试获取所有线程
        all_threads = calling.get_threads()
        assert len(all_threads) == 2

        # 测试只获取已完成的线程
        completed_threads = calling.get_threads(completed_only=True)
        assert len(completed_threads) == 1
        assert completed_threads[0].request_id == "thread1"

    def test_get_blocks(self, calling):
        """测试获取数据块"""
        # 添加测试数据
        thread = calling.get_or_create_thread("test_thread")
        block1 = StreamingBlock.create_block(
            BlockType.TEXT_CHUNK,
            text="test1",
            request_id="test_thread"
        )
        block2 = StreamingBlock.create_block(
            BlockType.ERROR,
            error="error",
            request_id="test_thread"
        )
        thread.add_block(block1)
        thread.add_block(block2)

        # 测试获取所有块
        all_blocks = calling.get_blocks("test_thread")
        assert len(all_blocks) == 2

        # 测试按类型获取块
        text_blocks = calling.get_blocks("test_thread", BlockType.TEXT_CHUNK)
        assert len(text_blocks) == 1
        assert text_blocks[0].block_type == BlockType.TEXT_CHUNK

        # 测试获取不存在线程的块
        nonexistent_blocks = calling.get_blocks("nonexistent")
        assert len(nonexistent_blocks) == 0

    def test_get_last_thread(self, calling):
        """测试获取最后一个线程"""
        # 空调用
        assert calling.get_last_thread() is None

        # 添加线程后测试
        thread1 = StreamingThread(request_id="thread1")
        thread2 = StreamingThread(request_id="thread2")
        calling.add_thread(thread1)
        calling.add_thread(thread2)
        assert calling.get_last_thread() == thread2

    def test_is_completed(self, calling):
        """测试完成状态检查"""
        # 空调用
        assert calling.is_completed()

        # 添加未完成线程
        thread1 = StreamingThread(request_id="thread1")
        calling.add_thread(thread1)
        assert not calling.is_completed()

        # 添加结束块
        end_block = StreamingBlock.create_block(BlockType.END)
        thread1.add_block(end_block)
        assert calling.is_completed()

        # 添加第二个未完成线程
        thread2 = StreamingThread(request_id="thread2")
        calling.add_thread(thread2)
        assert not calling.is_completed() 