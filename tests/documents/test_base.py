import pytest
import os
import json
import time
import shutil
import tempfile
import asyncio
import io
from pathlib import Path
from fastapi import UploadFile
import aiofiles
from unittest.mock import MagicMock, AsyncMock, patch

from illufly.documents.base import DocumentService, DocumentStatus, ProcessStage

# --------- 辅助函数和夹具 ---------

@pytest.fixture
def temp_base_dir():
    """创建临时基础目录"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield tmp_dir

@pytest.fixture
def docs_service(temp_base_dir):
    """创建文档服务实例"""
    return DocumentService(
        base_dir=temp_base_dir,
        max_file_size=5 * 1024 * 1024,  # 5MB
        max_total_size_per_user=10 * 1024 * 1024  # 10MB
    )

@pytest.fixture
def user_id():
    """测试用户ID"""
    return "test_user_123"

@pytest.fixture
def create_upload_file():
    """创建实际的UploadFile对象，使用真实临时文件"""
    temp_files = []
    temp_file_paths = []
    
    def _create_file(filename="test.pdf", content=b"test content"):
        # 创建临时文件
        temp_fd, temp_path = tempfile.mkstemp()
        temp_file_paths.append(temp_path)
        
        # 写入内容
        with os.fdopen(temp_fd, 'wb') as f:
            f.write(content)
        
        # 打开文件以供读取
        file_obj = open(temp_path, 'rb')
        temp_files.append(file_obj)
        
        # 创建UploadFile
        upload_file = UploadFile(filename=filename, file=file_obj)
        return upload_file
    
    yield _create_file
    
    # 测试完成后清理资源
    for file_obj in temp_files:
        file_obj.close()
    
    for path in temp_file_paths:
        try:
            os.unlink(path)
        except:
            pass

@pytest.fixture
def create_large_file():
    """创建大文件的UploadFile对象，使用真实临时文件"""
    temp_files = []
    temp_file_paths = []
    
    def _create_large_file(filename="large.pdf", size=6*1024*1024):
        # 创建临时文件
        temp_fd, temp_path = tempfile.mkstemp()
        temp_file_paths.append(temp_path)
        
        # 写入大量数据
        with os.fdopen(temp_fd, 'wb') as f:
            chunk_size = 1024 * 1024  # 1MB
            remaining = size
            
            while remaining > 0:
                write_size = min(chunk_size, remaining)
                f.write(b'x' * write_size)
                remaining -= write_size
        
        # 打开文件以供读取
        file_obj = open(temp_path, 'rb')
        temp_files.append(file_obj)
        
        # 创建UploadFile
        upload_file = UploadFile(filename=filename, file=file_obj)
        return upload_file
    
    yield _create_large_file
    
    # 测试完成后清理资源
    for file_obj in temp_files:
        file_obj.close()
    
    for path in temp_file_paths:
        try:
            os.unlink(path)
        except:
            pass

# --------- 测试用例 ---------

@pytest.mark.asyncio
async def test_save_document(docs_service, user_id, create_upload_file):
    """测试保存文档功能"""
    # 创建上传文件
    file = create_upload_file(filename="test_doc.pdf", content=b"PDF test content")
    
    # 保存文档
    doc_meta = await docs_service.save_document(user_id, file)
    
    # 验证返回的元数据
    assert doc_meta["document_id"] is not None
    assert doc_meta["original_name"] == "test_doc.pdf"
    assert doc_meta["type"] == "pdf"
    assert doc_meta["source_type"] == "local"
    assert doc_meta["status"] == DocumentStatus.ACTIVE
    assert doc_meta["process"]["current_stage"] == ProcessStage.NONE
    
    # 验证文件是否实际保存
    document_id = doc_meta["document_id"]
    raw_path = docs_service.get_raw_path(user_id, document_id)
    assert raw_path.exists()
    
    # 检查保存的文件内容
    with open(raw_path, 'rb') as f:
        saved_content = f.read()
        assert saved_content == b"PDF test content"
    
    # 验证元数据文件是否创建
    meta_path = docs_service.get_meta_path(user_id, document_id)
    assert meta_path.exists()
    
    # 检查元数据内容
    async with aiofiles.open(meta_path, 'r') as f:
        saved_meta = json.loads(await f.read())
        assert saved_meta["document_id"] == document_id
    
    # 检查文档是否存在
    assert await docs_service.document_exists(user_id, document_id)


@pytest.mark.asyncio
async def test_invalid_file_type(docs_service, user_id, create_upload_file):
    """测试不支持的文件类型"""
    # 创建不支持类型的文件
    file = create_upload_file(filename="test.xyz", content=b"unsupported content")
    
    # 尝试保存，应当抛出异常
    with pytest.raises(ValueError, match="不支持的文件类型"):
        await docs_service.save_document(user_id, file)


@pytest.mark.asyncio
async def test_create_remote_document(docs_service, user_id):
    """测试创建远程文档引用"""
    # 创建远程文档
    url = "https://example.com/sample.pdf"
    doc_meta = await docs_service.create_remote_document(user_id, url, "sample.pdf")
    
    # 验证元数据
    assert doc_meta["document_id"] is not None
    assert doc_meta["original_name"] == "sample.pdf"
    assert doc_meta["source_type"] == "remote"
    assert doc_meta["source_url"] == url
    
    # 验证元数据文件的存在
    document_id = doc_meta["document_id"]
    meta_path = docs_service.get_meta_path(user_id, document_id)
    assert meta_path.exists()
    
    # 检查文档是否存在
    assert await docs_service.document_exists(user_id, document_id)


@pytest.mark.asyncio
async def test_save_and_get_markdown(docs_service, user_id, create_upload_file):
    """测试保存和获取Markdown内容"""
    # 创建文档
    file = create_upload_file(filename="test_doc.pdf", content=b"PDF content")
    doc_meta = await docs_service.save_document(user_id, file)
    document_id = doc_meta["document_id"]
    
    # 保存Markdown内容
    markdown_content = "# Test Document\nThis is a test markdown"
    updated_meta = await docs_service.save_markdown(user_id, document_id, markdown_content)
    
    # 验证处理状态更新
    assert updated_meta["process"]["current_stage"] == ProcessStage.CONVERTED
    assert updated_meta["process"]["stages"]["conversion"]["stage"] == ProcessStage.CONVERTED
    assert updated_meta["process"]["stages"]["conversion"]["success"] is True
    
    # 读取Markdown内容
    retrieved_markdown = await docs_service.get_markdown(user_id, document_id)
    assert retrieved_markdown == markdown_content
    
    # 验证文件存在和内容
    md_path = docs_service.get_md_path(user_id, document_id)
    assert md_path.exists()
    
    with open(md_path, 'r') as f:
        file_content = f.read()
        assert file_content == markdown_content


@pytest.mark.asyncio
async def test_save_chunks(docs_service, user_id, create_upload_file):
    """测试保存和读取文档切片"""
    # 创建文档
    file = create_upload_file(filename="test_doc.pdf", content=b"PDF content")
    doc_meta = await docs_service.save_document(user_id, file)
    document_id = doc_meta["document_id"]
    
    # 创建测试切片
    chunks = [
        {"content": "Chunk 1 content", "metadata": {"page": 1}},
        {"content": "Chunk 2 content", "metadata": {"page": 1}},
        {"content": "Chunk 3 content", "metadata": {"page": 2}}
    ]
    
    # 保存切片
    success = await docs_service.save_chunks(user_id, document_id, chunks)
    assert success is True
    
    # 获取更新后的元数据
    updated_meta = await docs_service.get_document_meta(user_id, document_id)
    assert updated_meta["process"]["current_stage"] == ProcessStage.CHUNKED
    assert updated_meta["process"]["stages"]["chunking"]["stage"] == ProcessStage.CHUNKED
    assert updated_meta["process"]["stages"]["chunking"]["success"] is True
    assert "chunks" in updated_meta
    assert len(updated_meta["chunks"]) == 3
    
    # 读取切片并验证内容
    all_chunks = []
    async for chunk in docs_service.iter_chunks(user_id, document_id):
        all_chunks.append(chunk)
    
    assert len(all_chunks) == 3
    assert all_chunks[0]["content"] == "Chunk 1 content"
    assert all_chunks[0]["document_id"] == document_id
    assert all_chunks[0]["metadata"].get("page") == 1
    
    # 检查切片文件实际内容
    chunks_dir = docs_service.get_chunks_dir(user_id, document_id)
    assert chunks_dir.exists()
    
    chunk_files = list(chunks_dir.glob("*.txt"))
    assert len(chunk_files) == 3
    
    # 验证至少一个切片文件内容
    with open(chunk_files[0], 'r') as f:
        content = f.read()
        assert content in [chunk["content"] for chunk in chunks]


@pytest.mark.asyncio
async def test_calculate_storage_usage(docs_service, user_id, create_upload_file):
    """测试存储空间计算"""
    # 初始大小应为0
    initial_size = await docs_service.calculate_storage_usage(user_id)
    assert initial_size == 0
    
    # 准备文件内容
    content1 = b"Content 1" * 100  # ~900 bytes
    content2 = b"Content 2" * 200  # ~1800 bytes
    
    # 保存第一个文档
    file1 = create_upload_file(filename="doc1.pdf", content=content1)
    doc1 = await docs_service.save_document(user_id, file1)
    
    # 保存第二个文档
    file2 = create_upload_file(filename="doc2.pdf", content=content2)
    doc2 = await docs_service.save_document(user_id, file2)
    
    # 检查存储空间增加
    new_size = await docs_service.calculate_storage_usage(user_id)
    assert new_size > 0
    
    # 应该接近两个文件大小之和加上元数据大小
    expected_min = len(content1) + len(content2)
    assert new_size >= expected_min


@pytest.mark.asyncio
async def test_list_documents(docs_service, user_id, create_upload_file):
    """测试文档列表功能"""
    # 初始应该没有文档
    initial_docs = await docs_service.list_documents(user_id)
    assert len(initial_docs) == 0
    
    # 添加两个文档
    file1 = create_upload_file(filename="doc1.pdf", content=b"Content 1")
    doc1 = await docs_service.save_document(user_id, file1)
    
    file2 = create_upload_file(filename="doc2.pdf", content=b"Content 2")
    doc2 = await docs_service.save_document(user_id, file2)
    
    # 列出文档
    docs = await docs_service.list_documents(user_id)
    assert len(docs) == 2
    
    # 文档ID应该匹配
    doc_ids = {doc["document_id"] for doc in docs}
    assert doc1["document_id"] in doc_ids
    assert doc2["document_id"] in doc_ids


@pytest.mark.asyncio
async def test_delete_document(docs_service, user_id, create_upload_file):
    """测试文档删除功能"""
    # 创建文档
    file = create_upload_file(filename="to_delete.pdf", content=b"delete me")
    doc_meta = await docs_service.save_document(user_id, file)
    document_id = doc_meta["document_id"]
    
    # 确保文档存在
    assert await docs_service.document_exists(user_id, document_id)
    raw_path = docs_service.get_raw_path(user_id, document_id)
    assert raw_path.exists()
    
    # 删除文档
    result = await docs_service.delete_document(user_id, document_id)
    assert result is True
    
    # 验证文档不再存在
    assert not await docs_service.document_exists(user_id, document_id)
    assert not raw_path.exists()
    
    # 元数据文件也应该删除
    meta_path = docs_service.get_meta_path(user_id, document_id)
    assert not meta_path.exists()


@pytest.mark.asyncio
async def test_update_metadata(docs_service, user_id, create_upload_file):
    """测试元数据更新功能"""
    # 创建文档
    file = create_upload_file(filename="test_meta.pdf", content=b"metadata test")
    doc_meta = await docs_service.save_document(user_id, file)
    document_id = doc_meta["document_id"]
    
    # 更新元数据
    custom_meta = {
        "title": "Test Document",
        "description": "This is a test document",
        "tags": ["test", "sample"],
        "custom_field": {"key1": "value1"}
    }
    
    success = await docs_service.update_metadata(user_id, document_id, custom_meta)
    assert success is True
    
    # 验证更新后的元数据
    updated_meta = await docs_service.get_document_meta(user_id, document_id)
    assert updated_meta["title"] == "Test Document"
    assert updated_meta["description"] == "This is a test document"
    assert "test" in updated_meta["tags"]
    assert updated_meta["custom_field"]["key1"] == "value1"
    
    # 核心字段应保持不变
    assert updated_meta["document_id"] == document_id
    assert updated_meta["original_name"] == "test_meta.pdf"


@pytest.mark.asyncio
async def test_update_process_stage(docs_service, user_id, create_upload_file):
    """测试处理阶段状态更新"""
    # 创建文档
    file = create_upload_file(filename="stage_test.pdf", content=b"stage test")
    doc_meta = await docs_service.save_document(user_id, file)
    document_id = doc_meta["document_id"]
    
    # 更新处理阶段状态 - 转换中
    await docs_service.update_process_stage(
        user_id, document_id, "conversion",
        {
            "stage": ProcessStage.CONVERTING,
            "started_at": time.time(),
            "details": {"processor": "test_processor"}
        }
    )
    
    # 验证状态更新
    meta1 = await docs_service.get_document_meta(user_id, document_id)
    assert meta1["process"]["current_stage"] == ProcessStage.CONVERTING
    assert meta1["process"]["stages"]["conversion"]["stage"] == ProcessStage.CONVERTING
    assert meta1["process"]["stages"]["conversion"]["details"]["processor"] == "test_processor"
    
    # 更新为完成状态
    await docs_service.update_process_stage(
        user_id, document_id, "conversion",
        {
            "stage": ProcessStage.CONVERTED,
            "success": True,
            "finished_at": time.time()
        }
    )
    
    # 验证状态更新
    meta2 = await docs_service.get_document_meta(user_id, document_id)
    assert meta2["process"]["current_stage"] == ProcessStage.CONVERTED
    assert meta2["process"]["stages"]["conversion"]["stage"] == ProcessStage.CONVERTED
    assert meta2["process"]["stages"]["conversion"]["success"] is True
    assert meta2["process"]["stages"]["conversion"]["finished_at"] is not None


@pytest.mark.asyncio
async def test_document_exists(docs_service, user_id, create_upload_file):
    """测试文档存在性检查"""
    # 不存在的文档
    assert not await docs_service.document_exists(user_id, "nonexistent_id")
    
    # 创建文档
    file = create_upload_file(filename="exists_test.pdf", content=b"exists test")
    doc_meta = await docs_service.save_document(user_id, file)
    document_id = doc_meta["document_id"]
    
    # 文档应该存在
    assert await docs_service.document_exists(user_id, document_id)
    
    # 删除文档后应不存在
    await docs_service.delete_document(user_id, document_id)
    assert not await docs_service.document_exists(user_id, document_id)


@pytest.mark.asyncio
async def test_file_size_limit(docs_service, user_id, create_large_file):
    """测试文件大小限制"""
    # 创建超过限制的文件 (6MB > 5MB限制)
    file = create_large_file(filename="large.pdf", size=6*1024*1024)
    
    # 应该抛出大小限制异常
    with pytest.raises(ValueError, match="文件大小超过限制"):
        await docs_service.save_document(user_id, file)


@pytest.mark.asyncio
async def test_different_file_types(docs_service, user_id, create_upload_file):
    """测试不同类型文件的处理"""
    # 测试几种不同类型的文件
    file_types = [
        ("test.pdf", b"PDF content"),
        ("test.txt", b"Plain text content"),
        ("test.md", b"# Markdown content"),
        ("test.docx", b"DOCX content bytes"),
        ("test.jpg", b"JPEG image bytes")
    ]
    
    for filename, content in file_types:
        file = create_upload_file(filename=filename, content=content)
        doc_meta = await docs_service.save_document(user_id, file)
        
        # 验证基本信息
        assert doc_meta["document_id"] is not None
        assert doc_meta["original_name"] == filename
        
        # 获取文件类型（去掉前面的点）
        expected_type = filename.split(".")[-1]
        assert doc_meta["type"] == expected_type
        
        # 检查文件是否实际保存
        document_id = doc_meta["document_id"]
        raw_path = docs_service.get_raw_path(user_id, document_id)
        assert raw_path.exists()
        
        # 检查内容
        with open(raw_path, 'rb') as f:
            saved_content = f.read()
            assert saved_content == content


@pytest.mark.asyncio
async def test_multi_user_isolation(docs_service, create_upload_file):
    """测试多用户数据隔离"""
    user1 = "user_1"
    user2 = "user_2"
    
    # 用户1上传文件
    file1 = create_upload_file(filename="user1.pdf", content=b"User 1 content")
    doc1 = await docs_service.save_document(user1, file1)
    
    # 用户2上传同名文件
    file2 = create_upload_file(filename="user1.pdf", content=b"User 2 content")
    doc2 = await docs_service.save_document(user2, file2)
    
    # 确认两个文档ID不同
    assert doc1["document_id"] != doc2["document_id"]
    
    # 用户1只能看到自己的文档
    user1_docs = await docs_service.list_documents(user1)
    assert len(user1_docs) == 1
    assert user1_docs[0]["document_id"] == doc1["document_id"]
    
    # 用户2只能看到自己的文档
    user2_docs = await docs_service.list_documents(user2)
    assert len(user2_docs) == 1
    assert user2_docs[0]["document_id"] == doc2["document_id"]
    
    # 文件内容也是隔离的
    raw_path1 = docs_service.get_raw_path(user1, doc1["document_id"])
    with open(raw_path1, 'rb') as f:
        content1 = f.read()
        assert content1 == b"User 1 content"
    
    raw_path2 = docs_service.get_raw_path(user2, doc2["document_id"])
    with open(raw_path2, 'rb') as f:
        content2 = f.read()
        assert content2 == b"User 2 content"


@pytest.mark.asyncio
async def test_real_file_io(docs_service, user_id, temp_base_dir):
    """测试真实文件IO操作"""
    # 准备测试文件
    test_file_path = os.path.join(temp_base_dir, "test_real_io.txt")
    test_content = b"This is a real file IO test content."
    
    # 创建测试文件
    with open(test_file_path, "wb") as f:
        f.write(test_content)
    
    # 创建一个真实的文件对象
    with open(test_file_path, "rb") as file_obj:
        # 使用真实文件创建UploadFile
        upload_file = UploadFile(filename="real_test.txt", file=file_obj)
        
        # 保存文档
        doc_meta = await docs_service.save_document(user_id, upload_file)
        document_id = doc_meta["document_id"]
        
        # 验证文件已保存
        saved_path = docs_service.get_raw_path(user_id, document_id)
        assert saved_path.exists()
        
        # 验证内容
        with open(saved_path, "rb") as f:
            saved_content = f.read()
            assert saved_content == test_content

# ------------------- 向量索引和搜索测试 -------------------

class MockRetriever:
    """模拟向量检索器，用于测试"""
    
    async def add(self, texts, collection_name, user_id, metadatas):
        """模拟添加文档到向量索引"""
        return {
            "success": True,
            "added": len(texts),
            "skipped": 0,
            "original_count": len(texts)
        }
    
    async def ensure_index(self, collection_name):
        """模拟创建索引"""
        return True
    
    async def query(self, query_texts, collection_name, user_id, limit, filter=None):
        """模拟查询"""
        # 返回一个模拟的搜索结果
        return [{
            "query": query_texts,
            "results": [
                {
                    "text": "模拟搜索结果内容1",
                    "score": 0.85,
                    "metadata": {
                        "document_id": "doc_123",
                        "chunk_index": 0,
                        "title": "测试文档",
                        "original_name": "test_doc.pdf"
                    }
                },
                {
                    "text": "模拟搜索结果内容2",
                    "score": 0.75,
                    "metadata": {
                        "document_id": "doc_123",
                        "chunk_index": 1,
                        "title": "测试文档",
                        "original_name": "test_doc.pdf"
                    }
                }
            ]
        }]


@pytest.mark.asyncio
async def test_create_document_index(docs_service, user_id, create_upload_file):
    """测试创建文档向量索引"""
    # 创建一个文档
    file = create_upload_file(filename="test_doc.pdf", content=b"test_content")
    doc_meta = await docs_service.save_document(user_id, file)
    document_id = doc_meta["document_id"]
    
    # 保存Markdown内容
    markdown_content = "# test document\nthis is test content"
    await docs_service.save_markdown(user_id, document_id, markdown_content)
    
    # 创建切片
    chunks = [
        {"content": "test chunk content 1", "metadata": {"page": 1}},
        {"content": "test chunk content 2", "metadata": {"page": 2}}
    ]
    success = await docs_service.save_chunks(user_id, document_id, chunks)
    assert success is True
    
    # 创建一个模拟的向量检索器
    mock_retriever = MockRetriever()
    
    # 创建索引
    success = await docs_service.create_document_index(user_id, document_id, retriever=mock_retriever)
    assert success is True
    
    # 检查处理状态
    doc_meta = await docs_service.get_document_meta(user_id, document_id)
    assert doc_meta["process"]["current_stage"] == ProcessStage.INDEXED
    assert doc_meta["process"]["stages"]["indexing"]["stage"] == ProcessStage.INDEXED
    assert doc_meta["process"]["stages"]["indexing"]["success"] is True
    
    # 检查索引元数据
    assert "vector_index" in doc_meta
    assert doc_meta["vector_index"]["collection_name"] == f"user_{user_id}"
    assert doc_meta["vector_index"]["indexed_chunks"] == 2


@pytest.mark.asyncio
async def test_create_index_without_chunks(docs_service, user_id, create_upload_file):
    """测试在没有切片的情况下创建索引"""
    # 创建一个文档
    file = create_upload_file(filename="test_doc.pdf", content=b"test_content")
    doc_meta = await docs_service.save_document(user_id, file)
    document_id = doc_meta["document_id"]
    
    # 保存Markdown内容
    markdown_content = "# test document\nthis is test content"
    await docs_service.save_markdown(user_id, document_id, markdown_content)
    
    # 不保存切片
    
    # 创建一个模拟的向量检索器
    mock_retriever = MockRetriever()
    
    # 尝试创建索引，应该失败
    success = await docs_service.create_document_index(user_id, document_id, retriever=mock_retriever)
    assert success is False
    
    # 检查处理状态
    doc_meta = await docs_service.get_document_meta(user_id, document_id)
    assert doc_meta["process"]["stages"]["indexing"]["stage"] == ProcessStage.FAILED
    assert doc_meta["process"]["stages"]["indexing"]["success"] is False
    assert "error" in doc_meta["process"]["stages"]["indexing"]


@pytest.mark.asyncio
async def test_search_documents(docs_service, user_id, create_upload_file):
    """测试搜索文档"""
    # 创建一个文档
    file = create_upload_file(filename="test_doc.pdf", content=b"test_content")
    doc_meta = await docs_service.save_document(user_id, file)
    document_id = doc_meta["document_id"]
    
    # 保存Markdown内容
    markdown_content = "# test document\nthis is test content"
    await docs_service.save_markdown(user_id, document_id, markdown_content)
    
    # 创建切片
    chunks = [
        {"content": "test chunk content 1", "metadata": {"page": 1}},
        {"content": "test chunk content 2", "metadata": {"page": 2}}
    ]
    success = await docs_service.save_chunks(user_id, document_id, chunks)
    
    # 创建一个模拟的向量检索器
    mock_retriever = MockRetriever()
    
    # 创建索引
    success = await docs_service.create_document_index(user_id, document_id, retriever=mock_retriever)
    
    # 搜索文档
    results = await docs_service.search_documents(
        user_id=user_id,
        query="测试搜索查询",
        document_id=document_id,
        retriever=mock_retriever
    )
    
    # 验证搜索结果
    assert len(results) == 2
    assert results[0]["document_id"] == "doc_123"
    assert results[0]["content"] == "模拟搜索结果内容1"
    assert results[0]["score"] == 0.85
    
    # 测试没有指定文档ID的搜索
    results = await docs_service.search_documents(
        user_id=user_id,
        query="测试搜索查询",
        retriever=mock_retriever
    )
    
    # 验证搜索结果
    assert len(results) == 2


@pytest.mark.asyncio
async def test_search_nonexistent_collection(docs_service, user_id):
    """测试搜索不存在的集合"""
    # 创建一个模拟的向量检索器，模拟集合不存在
    class EmptyMockRetriever:
        async def query(self, query_texts, collection_name, user_id, limit, filter=None):
            return [{"query": query_texts, "results": []}]
    
    mock_retriever = EmptyMockRetriever()
    
    # 搜索不存在的集合
    results = await docs_service.search_documents(
        user_id=user_id,
        query="测试搜索查询",
        retriever=mock_retriever
    )
    
    # 验证结果为空
    assert len(results) == 0


@pytest.mark.asyncio
async def test_document_lifecycle(docs_service, user_id, create_upload_file):
    """测试文档完整生命周期：上传、转换、切片、索引、搜索、删除"""
    # 1. 上传文档
    file = create_upload_file(filename="lifecycle.pdf", content=b"lifecycle test content")
    doc_meta = await docs_service.save_document(user_id, file)
    document_id = doc_meta["document_id"]
    
    # 2. 转换为Markdown
    markdown_content = "# lifecycle test document\nthis is lifecycle test content"
    await docs_service.save_markdown(user_id, document_id, markdown_content)
    
    # 3. 创建切片
    chunks = [
        {"content": "lifecycle test chunk content 1", "metadata": {"page": 1}},
        {"content": "lifecycle test chunk content 2", "metadata": {"page": 2}}
    ]
    await docs_service.save_chunks(user_id, document_id, chunks)
    
    # 4. 创建索引
    mock_retriever = MockRetriever()
    await docs_service.create_document_index(user_id, document_id, retriever=mock_retriever)
    
    # 5. 搜索文档
    results = await docs_service.search_documents(
        user_id=user_id,
        query="lifecycle test",
        document_id=document_id,
        retriever=mock_retriever
    )
    assert len(results) > 0
    
    # 6. 删除文档
    success = await docs_service.delete_document(user_id, document_id)
    assert success is True
    
    # 7. 验证删除后无法搜索
    # 这需要修改 MockRetriever 的行为，让它在文档被删除后返回空结果
    # 但对于测试目的，我们可以简单验证文档不再存在
    assert not await docs_service.document_exists(user_id, document_id)
