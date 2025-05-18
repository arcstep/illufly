import os
import pytest
import asyncio
import time
from pathlib import Path
from illufly.documents.path_manager import PathManager
from illufly.documents.md_indexing import MarkdownIndexing

# 标记整个测试模块使用asyncio
pytestmark = pytest.mark.asyncio

class TestMarkdownIndexing:
    @pytest.fixture
    def path_manager(self, tmpdir):
        """创建PathManager实例用于测试"""
        return PathManager(str(tmpdir))
    
    @pytest.fixture
    def md_indexing(self, path_manager):
        """创建MarkdownIndexing实例用于测试"""
        return MarkdownIndexing(path_manager)
    
    @pytest.fixture
    async def setup_test_data(self, path_manager):
        """设置测试数据：创建用户、主题和文档"""
        user1 = "test_user1"
        user2 = "test_user2"
        
        # 创建用户1的目录结构
        path_manager.create_topic_dir(user1, "topic1")
        path_manager.create_topic_dir(user1, "topic1/subtopic1")
        path_manager.create_topic_dir(user1, "topic2")
        
        # 创建用户1的文档
        user1_base = path_manager.get_user_base(user1)
        (user1_base / "__id_doc1__.md").write_text("测试文档1")
        (user1_base / "topic1" / "__id_doc2__.md").write_text("测试文档2")
        (user1_base / "topic1/subtopic1" / "__id_doc3__.md").write_text("测试文档3")
        (user1_base / "topic2" / "__id_doc4__.md").write_text("测试文档4")
        
        # 创建用户2的目录结构和文档
        path_manager.create_topic_dir(user2, "主题A")
        user2_base = path_manager.get_user_base(user2)
        (user2_base / "__id_doc5__.md").write_text("测试文档5")
        (user2_base / "主题A" / "__id_doc6__.md").write_text("测试文档6")
        
        return {"user1": user1, "user2": user2}
    
    async def test_refresh_index_empty(self, md_indexing):
        """测试刷新空索引"""
        user_id = "empty_user"
        
        # 刷新索引
        await md_indexing.refresh_index(user_id)
        
        # 验证结果
        assert user_id in md_indexing.index
        assert len(md_indexing.index[user_id]) == 0
        assert user_id in md_indexing.last_refresh
    
    async def test_refresh_index_with_documents(self, md_indexing, path_manager, setup_test_data):
        """测试刷新含有文档的索引"""
        user_id = setup_test_data["user1"]
        
        # 刷新索引
        await md_indexing.refresh_index(user_id)
        
        # 验证结果
        assert user_id in md_indexing.index
        assert len(md_indexing.index[user_id]) == 4
        assert "doc1" in md_indexing.index[user_id]
        assert "doc2" in md_indexing.index[user_id]
        assert "doc3" in md_indexing.index[user_id]
        assert "doc4" in md_indexing.index[user_id]
        
        # 验证路径信息
        assert md_indexing.index[user_id]["doc1"]["topic_path"] == "."
        assert md_indexing.index[user_id]["doc2"]["topic_path"] == "topic1"
        assert md_indexing.index[user_id]["doc3"]["topic_path"] == "topic1/subtopic1"
        assert md_indexing.index[user_id]["doc4"]["topic_path"] == "topic2"
    
    async def test_refresh_interval(self, md_indexing, setup_test_data):
        """测试刷新间隔机制"""
        user_id = setup_test_data["user1"]
        
        # 设置较短的刷新间隔用于测试
        md_indexing.refresh_interval = 1
        
        # 第一次刷新
        await md_indexing.refresh_index(user_id)
        first_refresh_time = md_indexing.last_refresh[user_id]
        
        # 立即刷新，应该被跳过
        await md_indexing.refresh_index(user_id)
        second_refresh_time = md_indexing.last_refresh[user_id]
        assert first_refresh_time == second_refresh_time
        
        # 等待刷新间隔
        time.sleep(1.1)
        
        # 再次刷新，应该更新时间戳
        await md_indexing.refresh_index(user_id)
        third_refresh_time = md_indexing.last_refresh[user_id]
        assert third_refresh_time > second_refresh_time
        
        # 强制刷新，忽略间隔
        time.sleep(0.1)  # 短暂等待，确保时间戳有差异
        await md_indexing.refresh_index(user_id, force=True)
        forced_refresh_time = md_indexing.last_refresh[user_id]
        assert forced_refresh_time > third_refresh_time
    
    async def test_get_document_path(self, md_indexing, setup_test_data):
        """测试获取文档路径"""
        user_id = setup_test_data["user1"]
        
        # 测试找到的情况
        topic_path = await md_indexing.get_document_path(user_id, "doc2")
        assert topic_path == "topic1"
        
        topic_path = await md_indexing.get_document_path(user_id, "doc3")
        assert topic_path == "topic1/subtopic1"
        
        # 测试不存在的情况
        topic_path = await md_indexing.get_document_path(user_id, "nonexistent")
        assert topic_path is None
    
    async def test_list_all_documents(self, md_indexing, setup_test_data):
        """测试列出所有文档"""
        user_id = setup_test_data["user1"]
        
        # 列出文档
        docs = await md_indexing.list_all_documents(user_id)
        
        # 验证结果
        assert len(docs) == 4
        doc_ids = [doc["document_id"] for doc in docs]
        assert "doc1" in doc_ids
        assert "doc2" in doc_ids
        assert "doc3" in doc_ids
        assert "doc4" in doc_ids
        
        # 验证每个文档都有路径
        for doc in docs:
            assert "topic_path" in doc
    
    async def test_update_document_path(self, md_indexing, setup_test_data):
        """测试更新文档路径"""
        user_id = setup_test_data["user1"]
        
        # 先刷新索引
        await md_indexing.refresh_index(user_id)
        
        # 更新路径
        old_path = md_indexing.index[user_id]["doc2"]["topic_path"]
        assert old_path == "topic1"
        
        await md_indexing.update_document_path(user_id, "doc2", "new_topic")
        
        # 验证路径已更新
        new_path = md_indexing.index[user_id]["doc2"]["topic_path"]
        assert new_path == "new_topic"
        
        # 验证时间戳已更新
        assert md_indexing.index[user_id]["doc2"]["last_checked"] > 0
    
    async def test_initialize(self, md_indexing, setup_test_data):
        """测试初始化索引"""
        # 设置回调函数进行测试
        callback_results = []
        
        async def test_callback(user_id, current, total):
            callback_results.append((user_id, current, total))
        
        # 初始化索引
        results = await md_indexing.initialize(callback=test_callback)
        
        # 验证结果
        assert len(results) == 2
        assert results[setup_test_data["user1"]] == 4
        assert results[setup_test_data["user2"]] == 2
        
        # 验证回调被正确调用
        assert len(callback_results) == 2
        assert callback_results[0][1] == 1  # current
        assert callback_results[1][1] == 2  # current
        assert callback_results[0][2] == 2  # total
        assert callback_results[1][2] == 2  # total
    
    async def test_get_stats(self, md_indexing, setup_test_data):
        """测试获取索引统计信息"""
        # 初始化索引
        await md_indexing.initialize()
        
        # 获取统计信息
        stats = await md_indexing.get_stats()
        
        # 验证结果
        assert stats["users"] == 2
        assert stats["documents"] == 6
        assert setup_test_data["user1"] in stats["user_stats"]
        assert setup_test_data["user2"] in stats["user_stats"]
        assert stats["user_stats"][setup_test_data["user1"]]["document_count"] == 4
        assert stats["user_stats"][setup_test_data["user2"]]["document_count"] == 2
    
    async def test_document_removed_from_index(self, md_indexing, path_manager, setup_test_data):
        """测试从文件系统删除文档后索引能否更新"""
        user_id = setup_test_data["user1"]
        
        # 先刷新索引
        await md_indexing.refresh_index(user_id)
        assert "doc2" in md_indexing.index[user_id]
        
        # 删除文档文件
        doc_path = path_manager.get_topic_path(user_id, "topic1/__id_doc2__.md")
        os.remove(doc_path)
        
        # 强制刷新索引
        await md_indexing.refresh_index(user_id, force=True)
        
        # 验证文档已从索引中删除
        assert "doc2" not in md_indexing.index[user_id]
    
    async def test_concurrent_index_access(self, md_indexing, setup_test_data):
        """测试并发访问索引"""
        user1 = setup_test_data["user1"]
        user2 = setup_test_data["user2"]
        
        # 创建多个协程同时刷新不同用户的索引
        task1 = asyncio.create_task(md_indexing.refresh_index(user1, force=True))
        task2 = asyncio.create_task(md_indexing.refresh_index(user2, force=True))
        
        # 等待任务完成
        await asyncio.gather(task1, task2)
        
        # 验证两个用户的索引都已正确刷新
        assert len(md_indexing.index[user1]) == 4
        assert len(md_indexing.index[user2]) == 2
