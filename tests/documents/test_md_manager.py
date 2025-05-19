import os
import pytest
import asyncio
import time
import json
import frontmatter
from pathlib import Path
from illufly.documents.md_manager import MarkdownManager

# 标记整个测试模块使用asyncio
pytestmark = pytest.mark.asyncio

class TestMarkdownManager:
    @pytest.fixture
    def md_manager(self, tmpdir):
        """创建MarkdownManager实例用于测试"""
        return MarkdownManager(str(tmpdir))
        
    @pytest.fixture
    async def setup_test_data(self, md_manager):
        """设置测试数据：创建用户、主题和文档"""
        user1 = "test_user1"
        user2 = "test_user2"
        
        # 创建用户1的目录结构
        await md_manager.create_topic(user1, "topic1")
        await md_manager.create_topic(user1, "topic1/subtopic1")
        await md_manager.create_topic(user1, "topic2")
        
        # 创建用户1的文档
        doc1_id = await md_manager.create_document(user1, "", "根目录文档", "测试文档1的内容")
        doc2_id = await md_manager.create_document(user1, "topic1", "主题1文档", "测试文档2的内容")
        doc3_id = await md_manager.create_document(user1, "topic1/subtopic1", "子主题文档", "测试文档3的内容")
        doc4_id = await md_manager.create_document(user1, "topic2", "主题2文档", "测试文档4的内容")
        
        # 创建带引用的文档
        doc_with_refs_id = await md_manager.create_document(
            user1, 
            "topic1", 
            "带引用的文档", 
            f"测试引用\n![图片](/images/test.png)\n[链接到文档](__id_{doc2_id}__.md)"
        )
        
        # 创建用户2的文档
        await md_manager.create_topic(user2, "主题A")
        doc5_id = await md_manager.create_document(user2, "", "用户2的文档", "测试文档5的内容")
        doc6_id = await md_manager.create_document(user2, "主题A", "用户2的主题文档", "测试文档6的内容")
        
        return {
            "user1": user1, 
            "user2": user2,
            "doc1_id": doc1_id, 
            "doc2_id": doc2_id, 
            "doc3_id": doc3_id, 
            "doc4_id": doc4_id,
            "doc_with_refs_id": doc_with_refs_id,
            "doc5_id": doc5_id,
            "doc6_id": doc6_id
        }
    
    # === 文档基本操作测试 ===
    async def test_create_document(self, md_manager):
        """测试创建文档"""
        user_id = "test_user_create"
        
        # 创建主题目录
        await md_manager.create_topic(user_id, "test_topic")
        
        # 创建简单文档
        doc_id = await md_manager.create_document(
            user_id, 
            "test_topic", 
            "测试文档", 
            "这是测试内容"
        )
        
        assert doc_id is not None
        
        # 创建带元数据的文档
        metadata = {
            "tags": ["测试", "示例"],
            "priority": "高",
            "created_by": "pytest"
        }
        
        doc_id2 = await md_manager.create_document(
            user_id, 
            "test_topic", 
            "带元数据的文档", 
            "这是带元数据的内容",
            metadata
        )
        
        assert doc_id2 is not None
        
        # 读取文档验证元数据
        doc = await md_manager.read_document(user_id, doc_id2)
        assert doc is not None
        assert doc["metadata"]["title"] == "带元数据的文档"
        assert doc["metadata"]["tags"] == ["测试", "示例"]
        assert doc["metadata"]["priority"] == "高"
        assert doc["metadata"]["created_by"] == "pytest"
        assert "created_at" in doc["metadata"]
        assert "updated_at" in doc["metadata"]
        assert "document_id" in doc["metadata"]
    
    async def test_read_document(self, md_manager, setup_test_data):
        """测试读取文档"""
        user_id = setup_test_data["user1"]
        doc_id = setup_test_data["doc2_id"]
        
        # 读取文档
        doc = await md_manager.read_document(user_id, doc_id)
        
        # 验证结果
        assert doc is not None
        assert doc["document_id"] == doc_id
        assert doc["content"] == "测试文档2的内容"
        assert doc["metadata"]["title"] == "主题1文档"
        assert doc["metadata"]["topic_path"] == "topic1"
        
        # 测试读取不存在的文档
        non_existent_doc = await md_manager.read_document(user_id, "non_existent_id")
        assert non_existent_doc is None
    
    async def test_update_document(self, md_manager, setup_test_data):
        """测试更新文档"""
        user_id = setup_test_data["user1"]
        doc_id = setup_test_data["doc1_id"]
        
        # 更新文档内容
        success = await md_manager.update_document(
            user_id, 
            doc_id, 
            content="更新后的内容"
        )
        assert success
        
        # 验证内容已更新
        doc = await md_manager.read_document(user_id, doc_id)
        assert doc["content"] == "更新后的内容"
        
        # 只更新元数据
        old_updated_at = doc["metadata"]["updated_at"]
        time.sleep(0.1)  # 确保时间戳有变化
        
        new_metadata = {
            "title": "新标题",
            "tags": ["已更新"]
        }
        
        success = await md_manager.update_document(
            user_id, 
            doc_id, 
            metadata=new_metadata
        )
        assert success
        
        # 验证元数据已更新
        doc = await md_manager.read_document(user_id, doc_id)
        assert doc["metadata"]["title"] == "新标题"
        assert doc["metadata"]["tags"] == ["已更新"]
        assert doc["metadata"]["updated_at"] > old_updated_at
        
        # 同时更新内容和元数据
        success = await md_manager.update_document(
            user_id, 
            doc_id, 
            content="内容和元数据同时更新",
            metadata={"priority": "低"}
        )
        assert success
        
        # 验证更新
        doc = await md_manager.read_document(user_id, doc_id)
        assert doc["content"] == "内容和元数据同时更新"
        assert doc["metadata"]["priority"] == "低"
    
    async def test_delete_document(self, md_manager, setup_test_data):
        """测试删除文档"""
        user_id = setup_test_data["user1"]
        doc_id = setup_test_data["doc4_id"]
        
        # 确认文档存在
        doc = await md_manager.read_document(user_id, doc_id)
        assert doc is not None
        
        # 删除文档
        success = await md_manager.delete_document(user_id, doc_id)
        assert success
        
        # 确认文档已删除
        doc = await md_manager.read_document(user_id, doc_id)
        assert doc is None
        
        # 尝试删除不存在的文档
        success = await md_manager.delete_document(user_id, "non_existent_id")
        assert not success
    
    # === 文档引用和资源测试 ===
    async def test_extract_references(self, md_manager):
        """测试提取文档中的引用"""
        # 测试内容
        content = """
# 测试文档
        
这里是一段文本，包含[普通链接](https://example.com)。

![图片1](/images/test1.png)
        
这里引用另一个文档[文档链接](__id_abc123__.md)
        
还有一个图片：![图片2](../resources/test2.jpg)
        
普通的本地文件链接[文件](../data.txt)
        """
        
        # 提取引用
        references = md_manager.extract_references(content)
        
        # 验证结果
        assert len(references["images"]) == 2
        assert "/images/test1.png" in references["images"]
        assert "../resources/test2.jpg" in references["images"]
        
        assert len(references["links"]) == 1
        assert "__id_abc123__.md" in references["links"]
    
    async def test_get_document_with_resources(self, md_manager, setup_test_data, tmpdir):
        """测试获取文档及其引用资源"""
        user_id = setup_test_data["user1"]
        doc_id = setup_test_data["doc_with_refs_id"]
        ref_doc_id = setup_test_data["doc2_id"]
        
        # 创建一个测试图片
        images_dir = Path(tmpdir) / user_id / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        test_image = images_dir / "test.png"
        test_image.write_bytes(b"fake image data")
        
        # 获取文档及其资源
        doc_with_resources = await md_manager.get_document_with_resources(
            user_id, 
            doc_id, 
            resolve_references=True
        )
        
        # 验证结果
        assert doc_with_resources is not None
        assert "references" in doc_with_resources
        
        # 验证图片引用
        assert len(doc_with_resources["references"]["images"]) == 1
        image_ref = doc_with_resources["references"]["images"][0]
        assert image_ref["path"] == "/images/test.png"
        assert not image_ref["exists"]  # 路径不匹配，所以应该不存在
        
        # 验证文档引用
        assert len(doc_with_resources["references"]["links"]) == 1
        link_ref = doc_with_resources["references"]["links"][0]
        assert link_ref["path"] == f"__id_{ref_doc_id}__.md"
        assert link_ref["exists"]
        assert link_ref["document_id"] == ref_doc_id
        assert link_ref["title"] == "主题1文档"
        assert "content" in link_ref
    
    # === 主题目录操作测试 ===
    async def test_create_and_get_topic_structure(self, md_manager):
        """测试创建主题目录并获取结构"""
        user_id = "test_user_topic"
        
        # 创建嵌套主题
        success = await md_manager.create_topic(user_id, "parent/child/grandchild")
        assert success
        
        # 创建一些文档
        doc1_id = await md_manager.create_document(user_id, "parent", "父主题文档", "内容1")
        doc2_id = await md_manager.create_document(user_id, "parent/child", "子主题文档", "内容2")
        
        # 获取主题结构
        structure = await md_manager.get_topic_structure(user_id, "parent")
        
        # 验证结构
        assert structure["user_id"] == user_id
        assert structure["path"] == "parent"
        assert len(structure["document_ids"]) == 1
        assert doc1_id in structure["document_ids"]
        assert "child" in structure["subtopics"]
        
        # 获取子主题结构
        child_structure = await md_manager.get_topic_structure(user_id, "parent/child")
        assert child_structure["path"] == "parent/child"
        assert len(child_structure["document_ids"]) == 1
        assert doc2_id in child_structure["document_ids"]
        assert "grandchild" in child_structure["subtopics"]
    
    async def test_rename_topic(self, md_manager, setup_test_data):
        """测试重命名主题"""
        user_id = setup_test_data["user1"]
        
        # 重命名主题
        success = await md_manager.rename_topic(user_id, "topic1", "renamed_topic")
        assert success
        
        # 验证主题已重命名
        structure = await md_manager.get_topic_structure(user_id, "")
        assert "renamed_topic" in structure["subtopics"]
        assert "topic1" not in structure["subtopics"]
        
        # 验证文档的元数据已更新
        doc_id = setup_test_data["doc2_id"]
        doc = await md_manager.read_document(user_id, doc_id)
        assert doc["metadata"]["topic_path"] == "renamed_topic"
    
    async def test_move_topic(self, md_manager, setup_test_data):
        """测试移动主题"""
        user_id = setup_test_data["user1"]
        
        # 移动主题
        success = await md_manager.move_topic(user_id, "topic1/subtopic1", "topic2")
        assert success
        
        # 验证主题已移动
        structure = await md_manager.get_topic_structure(user_id, "topic2")
        assert "subtopic1" in structure["subtopics"]
        
        # 验证源位置已不存在
        old_structure = await md_manager.get_topic_structure(user_id, "topic1")
        assert "subtopic1" not in old_structure["subtopics"]
        
        # 验证文档的元数据已更新
        doc_id = setup_test_data["doc3_id"]
        doc = await md_manager.read_document(user_id, doc_id)
        assert doc["metadata"]["topic_path"] == "topic2/subtopic1"
    
    async def test_copy_topic(self, md_manager, setup_test_data):
        """测试复制主题"""
        user_id = setup_test_data["user1"]
        
        # 复制主题
        success = await md_manager.copy_topic(user_id, "topic1", "topic2")
        assert success
        
        # 验证主题已复制
        structure = await md_manager.get_topic_structure(user_id, "topic2")
        assert "topic1" in structure["subtopics"]
        
        # 验证源主题仍存在
        old_structure = await md_manager.get_topic_structure(user_id, "")
        assert "topic1" in old_structure["subtopics"]
        
        # 验证复制的文档存在并且元数据正确
        # 获取topic2/topic1下的文档ID
        copied_structure = await md_manager.get_topic_structure(user_id, "topic2/topic1")
        assert len(copied_structure["document_ids"]) > 0
        
        # 检查其中一个文档的元数据
        copied_doc_id = copied_structure["document_ids"][0]
        doc = await md_manager.read_document(user_id, copied_doc_id)
        assert doc["metadata"]["topic_path"] == "topic2/topic1"
    
    async def test_merge_topics(self, md_manager, setup_test_data):
        """测试合并主题"""
        user_id = setup_test_data["user1"]
        
        # 在目标主题中创建冲突文档
        conflict_doc_id = await md_manager.create_document(
            user_id, 
            "topic2", 
            "冲突文档", 
            "这个文档将与source主题中的文档冲突"
        )
        
        # 先不覆盖合并
        success = await md_manager.merge_topics(user_id, "topic1", "topic2", overwrite=False)
        assert success
        
        # 验证目标主题包含源主题的文档
        merged_structure = await md_manager.get_topic_structure(user_id, "topic2")
        for doc_id in [setup_test_data["doc2_id"], setup_test_data["doc_with_refs_id"]]:
            doc = await md_manager.read_document(user_id, doc_id)
            assert doc is not None
            assert doc["metadata"]["topic_path"] == "topic2"
        
        # 确认冲突文档仍然存在
        conflict_doc = await md_manager.read_document(user_id, conflict_doc_id)
        assert conflict_doc is not None
    
    async def test_delete_topic(self, md_manager, setup_test_data):
        """测试删除主题"""
        user_id = setup_test_data["user1"]
        
        # 尝试删除非空主题（应该失败）
        success = await md_manager.delete_topic(user_id, "topic1", force=False)
        assert not success
        
        # 强制删除非空主题
        success = await md_manager.delete_topic(user_id, "topic1", force=True)
        assert success
        
        # 验证主题已删除
        structure = await md_manager.get_topic_structure(user_id, "")
        assert "topic1" not in structure["subtopics"]
        
        # 验证主题下的文档也已删除
        doc_id = setup_test_data["doc2_id"]
        doc = await md_manager.read_document(user_id, doc_id)
        assert doc is None
    
    # === 文档移动测试 ===
    async def test_move_document(self, md_manager, setup_test_data):
        """测试移动文档到另一个主题"""
        user_id = setup_test_data["user1"]
        doc_id = setup_test_data["doc1_id"]
        
        # 移动文档
        success = await md_manager.move_document(user_id, doc_id, "topic2")
        assert success
        
        # 验证文档已移动
        doc = await md_manager.read_document(user_id, doc_id)
        assert doc["metadata"]["topic_path"] == "topic2"
        
        # 创建目标目录不存在的情况
        doc_id = setup_test_data["doc2_id"]
        success = await md_manager.move_document(user_id, doc_id, "new_topic/nested")
        assert success
        
        # 验证文档已移动且新目录被创建
        doc = await md_manager.read_document(user_id, doc_id)
        assert doc["metadata"]["topic_path"] == "new_topic/nested"
        
        structure = await md_manager.get_topic_structure(user_id, "new_topic")
        assert "nested" in structure["subtopics"]
    
    # === 系统初始化和索引测试 ===
    async def test_initialize(self, md_manager, setup_test_data):
        """测试系统初始化"""
        # 设置回调函数进行测试
        callback_results = []
        
        async def test_callback(user_id, current, total):
            callback_results.append((user_id, current, total))
        
        # 初始化系统
        results = await md_manager.initialize(callback=test_callback)
        
        # 验证结果
        assert setup_test_data["user1"] in results
        assert setup_test_data["user2"] in results
        assert results[setup_test_data["user1"]] >= 4  # 至少有4个文档
        assert results[setup_test_data["user2"]] >= 2  # 至少有2个文档
        
        # 验证回调被正确调用
        assert len(callback_results) >= 2  # 至少两个用户
    
    async def test_save_and_load_cache(self, md_manager, setup_test_data, tmpdir):
        """测试保存和加载索引缓存"""
        # 先初始化索引
        await md_manager.initialize()
        
        # 保存缓存
        cache_file = str(tmpdir / "test_cache.json")
        success = await md_manager.save_cache(cache_file)
        assert success
        
        # 验证缓存文件存在
        assert os.path.exists(cache_file)
        
        # 验证文件内容
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        assert "timestamp" in cache_data
        assert "index" in cache_data
        assert setup_test_data["user1"] in cache_data["index"]
        
        # 创建新的管理器实例
        new_manager = MarkdownManager(str(tmpdir))
        
        # 加载缓存
        success = await new_manager.load_cache(cache_file)
        assert success
        
        # 验证索引已正确加载
        doc_id = setup_test_data["doc1_id"]
        doc = await new_manager.read_document(setup_test_data["user1"], doc_id)
        assert doc is not None
    
    async def test_verify_and_repair_document_paths(self, md_manager, setup_test_data):
        """测试验证和修复文档路径"""
        user_id = setup_test_data["user1"]
        doc_id = setup_test_data["doc2_id"]
        
        # 手动修改元数据中的路径（制造不一致）
        doc = await md_manager.read_document(user_id, doc_id)
        doc["metadata"]["topic_path"] = "错误的路径"
        await md_manager.update_document(user_id, doc_id, metadata=doc["metadata"])
        
        # 验证和修复
        await md_manager.verify_and_repair_document_paths(user_id, "topic1")
        
        # 检查是否已修复
        doc = await md_manager.read_document(user_id, doc_id)
        assert doc["metadata"]["topic_path"] == "topic1"

    async def test_index_repair_after_file_system_changes(self, md_manager, setup_test_data):
        """测试文件系统直接修改后的索引修复"""
        user_id = setup_test_data["user1"]
        doc_id = setup_test_data["doc1_id"]
        
        # 获取原始文档信息
        doc = await md_manager.read_document(user_id, doc_id)
        old_path = Path(doc["file_path"])
        original_topic_path = doc["metadata"]["topic_path"]
        
        # 直接通过文件系统移动文件，绕过索引更新
        new_dir = md_manager.get_topic_path(user_id, "manually_moved")
        new_dir.mkdir(exist_ok=True)
        new_path = new_dir / old_path.name
        old_path.rename(new_path)
        
        # 直接从索引获取路径（不触发文件系统搜索）
        index_path = await md_manager.index_manager.get_document_path(user_id, doc_id)
        # 验证索引中的路径仍然是旧路径
        assert index_path == original_topic_path
        
        # 尝试读取文档（应该能找到，是通过文件系统搜索找到的）
        doc1 = await md_manager.read_document(user_id, doc_id)
        assert doc1 is not None
        assert "manually_moved" in doc1["file_path"]
        # 元数据中的路径还是旧的
        assert doc1["metadata"]["topic_path"] == original_topic_path
        
        # 强制刷新索引
        await md_manager.index_manager.refresh_index(user_id, force=True)
        
        # 再次直接从索引获取路径
        updated_index_path = await md_manager.index_manager.get_document_path(user_id, doc_id)
        # 验证索引已更新为新路径
        assert updated_index_path == "manually_moved"
        
        # 修复元数据
        await md_manager.verify_and_repair_document_paths(user_id, "manually_moved")
        
        # 再次读取文档，验证元数据也已更新
        doc2 = await md_manager.read_document(user_id, doc_id)
        assert doc2["metadata"]["topic_path"] == "manually_moved"

    async def test_concurrent_operations(self, md_manager, setup_test_data):
        """测试并发操作下的索引一致性"""
        user_id = setup_test_data["user1"]
        
        # 创建多个并发任务
        async def create_and_move_docs():
            doc_ids = []
            for i in range(10):
                doc_id = await md_manager.create_document(user_id, f"topic{i%3}", f"并发文档{i}")
                doc_ids.append(doc_id)
            return doc_ids
        
        # 并发执行多个任务
        tasks = [create_and_move_docs() for _ in range(5)]
        results = await asyncio.gather(*tasks)
        
        # 验证所有文档都能正确访问
        for doc_ids in results:
            for doc_id in doc_ids:
                doc = await md_manager.read_document(user_id, doc_id)
                assert doc is not None
