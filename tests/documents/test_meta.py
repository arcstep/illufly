import pytest
import tempfile
import asyncio
import json
import time
from pathlib import Path

from illufly.documents.meta import DocumentMetaManager, DocumentMeta


@pytest.fixture
def temp_dir():
    """创建临时目录用于测试"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def meta_manager(temp_dir):
    """创建元数据管理器实例"""
    meta_dir = f"{temp_dir}/meta"
    docs_dir = f"{temp_dir}/docs"
    return DocumentMetaManager(meta_dir, docs_dir)


@pytest.fixture
def user_id():
    """测试用户ID"""
    return "test_user"


@pytest.fixture
def document_id():
    """测试文档ID"""
    return "test_doc_123"


@pytest.mark.asyncio
async def test_init(temp_dir):
    """测试元数据管理器初始化"""
    meta_dir = f"{temp_dir}/meta"
    docs_dir = f"{temp_dir}/docs"
    manager = DocumentMetaManager(meta_dir, docs_dir)
    
    # 验证基础目录已创建
    assert Path(docs_dir).exists()
    assert Path(docs_dir).is_dir()


@pytest.mark.asyncio
async def test_get_user_base(meta_manager, user_id):
    """测试获取用户根目录"""
    user_base = meta_manager.get_user_base(user_id)
    assert user_base.exists()
    assert user_base.is_dir()
    assert user_base == Path(meta_manager.docs_dir) / user_id


@pytest.mark.asyncio
async def test_get_document_path(meta_manager, user_id, document_id):
    """测试获取文档路径"""
    # 无主题路径
    doc_path = meta_manager.get_document_path(user_id, None, document_id)
    expected_path = meta_manager.get_user_base(user_id) / f"__id_{document_id}__"
    assert doc_path == expected_path
    assert doc_path.exists()
    
    # 有主题路径
    topic_path = "topic1/subtopic1"
    doc_path_with_topic = meta_manager.get_document_path(user_id, topic_path, document_id)
    expected_path_with_topic = meta_manager.get_user_base(user_id) / topic_path / f"__id_{document_id}__"
    assert doc_path_with_topic == expected_path_with_topic
    assert doc_path_with_topic.exists()


@pytest.mark.asyncio
async def test_create_document(meta_manager, user_id, document_id):
    """测试创建文档元数据"""
    # 创建基础文档
    topic_path = "test_topic"
    meta = await meta_manager.create_document(user_id, document_id, topic_path)
    
    # 验证返回的元数据
    assert meta["document_id"] == document_id
    assert meta["user_id"] == user_id
    assert meta["topic_path"] == topic_path
    assert meta["processed"] == False  # 初始状态未处理
    assert "created_at" in meta
    assert "updated_at" in meta
    
    # 验证文件夹已创建
    folder_path = meta_manager.get_document_path(user_id, topic_path, document_id)
    assert folder_path.exists()
    
    # 测试带初始元数据
    doc_id2 = "doc_with_initial_meta"
    initial_meta = {
        "original_name": "test.pdf",
        "type": "pdf",
        "size": 1024
    }
    meta2 = await meta_manager.create_document(user_id, doc_id2, topic_path, initial_meta)
    assert meta2["original_name"] == "test.pdf"
    assert meta2["type"] == "pdf"
    assert meta2["size"] == 1024


@pytest.mark.asyncio
async def test_get_metadata(meta_manager, user_id, document_id):
    """测试获取元数据"""
    # 先创建文档
    topic_path = "test_topic"
    await meta_manager.create_document(user_id, document_id, topic_path)
    
    # 获取元数据
    meta = await meta_manager.get_metadata(user_id, document_id)
    assert meta is not None
    assert meta["document_id"] == document_id
    assert meta["user_id"] == user_id
    assert meta["topic_path"] == topic_path
    
    # 获取不存在的文档
    nonexistent_meta = await meta_manager.get_metadata(user_id, "nonexistent_doc")
    assert nonexistent_meta is None


@pytest.mark.asyncio
async def test_update_metadata(meta_manager, user_id, document_id):
    """测试更新元数据"""
    # 先创建文档
    topic_path = "test_topic"
    original_meta = await meta_manager.create_document(user_id, document_id, topic_path)
    original_updated_at = original_meta["updated_at"]
    
    # 等待一小段时间确保时间戳会更新
    await asyncio.sleep(0.01)
    
    # 更新元数据
    update_data = {
        "type": "pdf",
        "original_name": "updated.pdf",
        "metadata": {
            "custom_key": "custom_value"
        }
    }
    updated_meta = await meta_manager.update_metadata(user_id, document_id, update_data)
    
    # 验证更新
    assert updated_meta["type"] == "pdf"
    assert updated_meta["original_name"] == "updated.pdf"
    assert updated_meta["metadata"]["custom_key"] == "custom_value"
    assert updated_meta["updated_at"] > original_updated_at
    
    # 再次获取确认持久化
    retrieved_meta = await meta_manager.get_metadata(user_id, document_id)
    assert retrieved_meta["type"] == "pdf"
    assert retrieved_meta["original_name"] == "updated.pdf"
    assert retrieved_meta["metadata"]["custom_key"] == "custom_value"
    
    # 测试深度合并
    nested_update = {
        "metadata": {
            "nested_key": "nested_value"
        }
    }
    deep_updated_meta = await meta_manager.update_metadata(user_id, document_id, nested_update)
    assert deep_updated_meta["metadata"]["custom_key"] == "custom_value"  # 原值保留
    assert deep_updated_meta["metadata"]["nested_key"] == "nested_value"  # 新值添加


@pytest.mark.asyncio
async def test_delete_document(meta_manager, user_id, document_id):
    """测试删除文档"""
    # 先创建文档
    topic_path = "test_topic"
    await meta_manager.create_document(user_id, document_id, topic_path)
    
    # 确认文档存在
    doc_path = meta_manager.get_document_path(user_id, topic_path, document_id)
    assert doc_path.exists()
    meta = await meta_manager.get_metadata(user_id, document_id)
    assert meta is not None
    
    # 删除文档
    result = await meta_manager.delete_document(user_id, document_id)
    assert result is True
    
    # 确认文档已删除
    assert not doc_path.exists()
    deleted_meta = await meta_manager.get_metadata(user_id, document_id)
    assert deleted_meta is None
    
    # 测试删除不存在的文档
    nonexistent_result = await meta_manager.delete_document(user_id, "nonexistent_doc")
    assert nonexistent_result is True  # 不存在也返回成功


@pytest.mark.asyncio
async def test_list_documents(meta_manager, user_id):
    """测试列出文档"""
    # 创建多个文档
    topic1 = "topic1"
    topic2 = "topic2"
    
    doc1 = "doc1"
    doc2 = "doc2"
    doc3 = "doc3"
    
    await meta_manager.create_document(user_id, doc1, topic1)
    await meta_manager.create_document(user_id, doc2, topic1)
    await meta_manager.create_document(user_id, doc3, topic2)
    
    # 列出所有文档
    all_docs = await meta_manager.list_documents(user_id)
    assert len(all_docs) == 3
    doc_ids = {doc["document_id"] for doc in all_docs}
    assert doc_ids == {doc1, doc2, doc3}
    
    # 按主题列出文档
    topic1_docs = await meta_manager.list_documents(user_id, topic1)
    assert len(topic1_docs) == 2
    topic1_ids = {doc["document_id"] for doc in topic1_docs}
    assert topic1_ids == {doc1, doc2}
    
    # 空主题
    empty_topic_docs = await meta_manager.list_documents(user_id, "empty_topic")
    assert len(empty_topic_docs) == 0


@pytest.mark.asyncio
async def test_document_folder_functions(meta_manager):
    """测试文档目录名称相关功能"""
    # 测试文件夹名检查
    assert meta_manager.is_document_folder("__id_test123__") is True
    assert meta_manager.is_document_folder("normal_folder") is False
    assert meta_manager.is_document_folder("_id_test_") is False
    
    # 测试提取文档ID
    assert meta_manager.extract_document_id("__id_test123__") == "test123"
    assert meta_manager.extract_document_id("normal_folder") is None
    
    # 测试生成文件夹名
    assert meta_manager.get_document_folder_name("test123") == "__id_test123__"


@pytest.mark.asyncio
async def test_get_topic_path(meta_manager, user_id, document_id):
    """测试从元数据获取主题路径"""
    # 创建带主题的文档
    topic_path = "test/nested/topic"
    await meta_manager.create_document(user_id, document_id, topic_path)
    
    # 获取主题路径
    retrieved_path = await meta_manager._get_topic_path(user_id, document_id)
    assert retrieved_path == topic_path
    
    # 测试不存在的文档
    nonexistent_path = await meta_manager._get_topic_path(user_id, "nonexistent")
    assert nonexistent_path is None


@pytest.mark.asyncio
async def test_processed_documents(meta_manager, user_id):
    """测试查找已处理/未处理的文档"""
    # 创建测试文档
    doc1 = "processed_doc1"
    doc2 = "processed_doc2" 
    doc3 = "unprocessed_doc"
    
    # 创建并标记为已处理/未处理
    await meta_manager.create_document(user_id, doc1)
    await meta_manager.update_metadata(user_id, doc1, {"processed": True})
    
    await meta_manager.create_document(user_id, doc2)
    await meta_manager.update_metadata(user_id, doc2, {"processed": True})
    
    await meta_manager.create_document(user_id, doc3)
    
    # 查询已处理文档
    processed_docs = await meta_manager.find_processed_documents(user_id, True)
    assert len(processed_docs) == 2
    processed_ids = {doc["document_id"] for doc in processed_docs}
    assert processed_ids == {doc1, doc2}
    
    # 查询未处理文档
    unprocessed_docs = await meta_manager.find_processed_documents(user_id, False)
    assert len(unprocessed_docs) == 1
    assert unprocessed_docs[0]["document_id"] == doc3