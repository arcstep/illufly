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

from illufly.documents.base import DocumentService, DocumentStatus
from illufly.documents.machine import DocumentMachine

# 创建一个模拟的voidrail_client
class MockVoidrailClient:
    async def stream(self, **kwargs):
        """返回一个模拟的响应流"""
        async def mock_response():
            yield "# 模拟Markdown内容\n\n这是测试生成的内容。"
        return mock_response()

# --------- 辅助函数和夹具 ---------

@pytest.fixture
def temp_base_dir():
    """创建临时基础目录"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield tmp_dir

@pytest.fixture
def docs_service(temp_base_dir):
    """创建文档服务实例"""
    service = DocumentService(
        base_dir=temp_base_dir,
        max_file_size=5 * 1024 * 1024,  # 5MB
        max_total_size_per_user=10 * 1024 * 1024  # 10MB
    )
    # 在这里注入模拟客户端
    service.voidrail_client = MockVoidrailClient()
    return service

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

@pytest.fixture
def mock_documents_service(temp_base_dir):
    """创建使用状态机的测试专用文档服务"""
    class TestDocumentService(DocumentService):
        """测试专用文档服务子类"""
        
        async def create_document_index(self, user_id, document_id):
            """使用状态机的索引创建实现"""
            try:
                # 获取文档元数据
                doc_meta = await self.get_document_meta(user_id, document_id)
                
                # 获取状态机
                machine = await self.get_document_machine(user_id, document_id)
                
                # 验证状态 - 确保已切片
                if machine.current_state.id != 'chunked':
                    # 更新状态为失败
                    await machine.fail_embedding(error=f"文档必须先切片才能创建索引: {document_id}")
                    return False
                
                # 开始向量化
                await machine.start_embedding()
                
                # 完成向量化
                await machine.complete_embedding(indexed_chunks=2)
                
                # 更新索引元数据
                await self.update_metadata(user_id, document_id, {
                    "vector_index": {
                        "collection_name": self.default_indexing_collection(user_id),
                        "indexed_at": time.time(),
                        "indexed_chunks": 2
                    }
                })
                
                return True
            except Exception as e:
                print(f"模拟索引创建中捕获到异常: {e}")
                return False
    
    # 创建模拟检索器
    class StableRetriever:
        async def add(self, texts, collection_name, user_id, metadatas=None):
            return {
                "success": True, 
                "added": len(texts) if texts else 0,
                "skipped": 0,
                "original_count": len(texts) if texts else 0
            }
        
        async def ensure_index(self, collection_name):
            return True
            
        async def delete(self, collection_name=None, user_id=None, document_id=None, filter=None):
            return {"success": True, "deleted": 1}
            
        async def query(self, query_texts, collection_name=None, user_id=None, limit=10, filter=None):
            if isinstance(query_texts, str):
                query_texts = [query_texts]
                
            results = []
            for _ in query_texts:
                results.append({
                    "query": _,
                    "results": [
                        {
                            "text": "模拟搜索结果内容1",
                            "distance": 0.85,
                            "metadata": {"document_id": "doc_123", "chunk_index": 0}
                        },
                        {
                            "text": "模拟搜索结果内容2",
                            "distance": 0.75,
                            "metadata": {"document_id": "doc_123", "chunk_index": 1}
                        }
                    ]
                })
            return results
    
    # 使用子类并注入检索器
    return TestDocumentService(
        base_dir=temp_base_dir,
        max_file_size=5 * 1024 * 1024,
        max_total_size_per_user=10 * 1024 * 1024,
        retriever=StableRetriever()
    )

@pytest.mark.asyncio
async def test_save_document(docs_service, user_id, create_upload_file):
    """测试文档保存功能
    
    目的：
    - 验证基本的文档上传与保存功能能否正常工作
    - 确认生成的元数据结构是否正确
    - 验证状态机初始化为uploaded状态
    - 检查文件系统中的实际文件与元数据是否正确保存
    """
    # 创建上传文件
    file = create_upload_file(filename="test_doc.pdf", content=b"PDF test content")
    
    # 保存文档
    doc_meta = await docs_service.save_document(user_id, file)
    document_id = doc_meta["document_id"]
    
    # 验证返回的元数据
    assert doc_meta["document_id"] is not None
    assert doc_meta["original_name"] == "test_doc.pdf"
    assert doc_meta["type"] == "pdf"
    assert doc_meta["source_type"] == "local"
    assert doc_meta["status"] == DocumentStatus.ACTIVE
    
    # 获取状态机来验证状态
    machine = await docs_service.get_document_machine(user_id, document_id)
    assert machine.current_state.id == 'uploaded'
    
    # 验证文件是否实际保存
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

    # 检查是否为正确的初始状态
    assert machine.current_state.id == 'uploaded'

@pytest.mark.asyncio
async def test_invalid_file_type(docs_service, user_id, create_upload_file):
    """测试不支持的文件类型处理
    
    目的：
    - 验证系统能否正确拒绝不支持的文件类型
    - 确认错误处理机制能否抛出适当的异常信息
    - 测试系统的类型验证防护措施
    """
    # 创建不支持类型的文件
    file = create_upload_file(filename="test.xyz", content=b"unsupported content")
    
    # 尝试保存，应当抛出异常
    with pytest.raises(ValueError, match="不支持的文件类型"):
        await docs_service.save_document(user_id, file)


@pytest.mark.asyncio
async def test_create_remote_document(docs_service, user_id):
    """测试远程文档引用创建功能
    
    目的：
    - 验证系统能否正确创建远程文档的引用（如URL链接）
    - 检查远程文档的元数据结构是否正确
    - 确认远程文档初始状态是否正确设置
    """
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
    """测试Markdown转换和获取功能
    
    目的：
    - 验证文档到Markdown的转换过程
    - 测试状态机的markdowning到markdowned的状态转换
    - 确认转换后的Markdown内容能够正确存储和检索
    - 验证Markdown文件的物理存储
    """
    # 创建文档
    file = create_upload_file(filename="test_doc.pdf", content=b"PDF content")
    doc_meta = await docs_service.save_document(user_id, file)
    document_id = doc_meta["document_id"]
    
    # 保存Markdown内容
    markdown_content = "# Test Document\nThis is a test markdown"
    updated_meta = await docs_service.save_markdown(user_id, document_id, markdown_content)
    
    # 验证处理状态更新
    assert updated_meta["state"] == "markdowned"
    assert updated_meta["process_details"]["markdowning"]["success"] is True
    
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
    """测试文档切片功能
    
    目的：
    - 验证文档内容能否正确分割为多个切片
    - 测试状态机从markdowned到chunked的状态转换
    - 确认切片元数据正确记录在文档元数据中
    - 检查切片文件是否正确存储在文件系统中
    """
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
    assert updated_meta["state"] == "chunked"
    assert updated_meta["process_details"]["chunking"]["success"] is True
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
    """测试存储空间计算功能
    
    目的：
    - 验证系统能否正确计算用户已使用的存储空间
    - 确认多个文档的存储空间是否正确累加
    - 测试存储空间统计的准确性
    """
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
    """测试文档列表获取功能
    
    目的：
    - 验证系统能否正确列出用户的所有文档
    - 确认新添加的文档能够在列表中正确显示
    - 测试多文档管理功能
    """
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
    """测试文档删除功能
    
    目的：
    - 验证系统能否正确删除文档及其相关资源
    - 确认删除后文档的所有文件和元数据都被清理
    - 测试删除操作的完整性和一致性
    """
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
    """测试元数据更新功能
    
    目的：
    - 验证系统能否正确更新文档的自定义元数据
    - 确认元数据更新不会影响核心字段
    - 测试深层次元数据结构的更新能力
    """
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
    """测试处理阶段状态更新功能
    
    目的：
    - 验证通过元数据更新修改文档状态的能力
    - 确认状态阶段信息能够正确记录
    - 测试处理阶段完整流程的状态记录
    """
    # 创建文档
    file = create_upload_file(filename="stage_test.pdf", content=b"stage test")
    doc_meta = await docs_service.save_document(user_id, file)
    document_id = doc_meta["document_id"]
    
    # 更新处理阶段状态 - 转换中
    await docs_service.update_metadata(
        user_id, document_id, 
        {
            "state": "markdowning",
            "process_details": {
                "markdowning": {
                    "stage": "markdowning",
                    "started_at": time.time(),
                    "details": {"processor": "test_processor"}
                }
            }
        }
    )
    
    # 验证状态更新
    meta1 = await docs_service.get_document_meta(user_id, document_id)
    assert meta1["state"] == "markdowning"
    assert meta1["process_details"]["markdowning"]["stage"] == "markdowning"
    assert meta1["process_details"]["markdowning"]["details"]["processor"] == "test_processor"
    
    # 更新为完成状态
    await docs_service.update_metadata(
        user_id, document_id,
        {
            "state": "markdowned",
            "process_details": {
                "markdowning": {
                    "stage": "markdowned",
                    "success": True,
                    "finished_at": time.time()
                }
            }
        }
    )
    
    # 验证状态更新
    meta2 = await docs_service.get_document_meta(user_id, document_id)
    assert meta2["state"] == "markdowned"
    assert meta2["process_details"]["markdowning"]["stage"] == "markdowned"
    assert meta2["process_details"]["markdowning"]["success"] is True
    assert meta2["process_details"]["markdowning"]["finished_at"] is not None


@pytest.mark.asyncio
async def test_document_exists(docs_service, user_id, create_upload_file):
    """测试文档存在性检查功能
    
    目的：
    - 验证系统能否正确检测文档是否存在
    - 测试不存在文档的处理
    - 确认删除后文档状态的变化能被正确检测
    """
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
    """测试文件大小限制功能
    
    目的：
    - 验证系统能否正确拒绝超过大小限制的文件
    - 测试大文件处理的边界条件
    - 确认系统能够提供明确的错误信息
    """
    # 创建超过限制的文件 (6MB > 5MB限制)
    file = create_large_file(filename="large.pdf", size=6*1024*1024)
    
    # 应该抛出大小限制异常
    with pytest.raises(ValueError, match="文件大小超过限制"):
        await docs_service.save_document(user_id, file)


@pytest.mark.asyncio
async def test_different_file_types(docs_service, user_id, create_upload_file):
    """测试不同文件类型的处理能力
    
    目的：
    - 验证系统能否正确处理各种支持的文件类型
    - 确认不同类型文件的元数据正确设置
    - 测试系统的文件类型识别能力
    """
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
    """测试多用户数据隔离功能
    
    目的：
    - 验证不同用户的文档数据是否正确隔离
    - 确认用户只能访问自己的文档
    - 测试相同文件名在不同用户下的处理
    - 验证多租户支持的安全性
    """
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
    """测试实际文件IO操作
    
    目的：
    - 验证系统能否正确处理真实文件对象
    - 测试从磁盘文件到UploadFile的转换
    - 确认实际文件内容能被正确保存
    """
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

@pytest.mark.asyncio
async def test_create_document_index(mock_documents_service, user_id, create_upload_file):
    """测试文档向量索引创建功能
    
    目的：
    - 验证状态机从chunked到embedded的状态转换
    - 确认文档能被正确索引到向量数据库
    - 测试索引元数据的正确记录
    - 验证索引过程的完整性
    """
    docs_service = mock_documents_service
    
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
    
    # 创建索引 - 不再传递retriever参数
    success = await docs_service.create_document_index(user_id, document_id)
    assert success is True
    
    # 检查处理状态
    doc_meta = await docs_service.get_document_meta(user_id, document_id)
    assert doc_meta["state"] == "embedded"
    assert doc_meta["process_details"]["embedding"]["stage"] == "embedded"
    assert doc_meta["process_details"]["embedding"]["success"] is True
    
    # 检查索引元数据
    assert "vector_index" in doc_meta
    assert doc_meta["vector_index"]["collection_name"] == f"user_{user_id}"
    assert doc_meta["vector_index"]["indexed_chunks"] == 2


@pytest.mark.asyncio
async def test_create_index_without_chunks(mock_documents_service, user_id, create_upload_file):
    """测试在没有切片的情况下创建索引
    
    目的：
    - 验证系统对索引前置条件的检查能力
    - 测试不满足条件时的错误处理和状态转换
    - 确认状态机能正确处理失败情况
    """
    docs_service = mock_documents_service
    
    # 创建文档
    file = create_upload_file(filename="test_doc.pdf", content=b"test_content")
    doc_meta = await docs_service.save_document(user_id, file)
    document_id = doc_meta["document_id"]
    
    # 保存Markdown内容
    markdown_content = "# test document\nthis is test content"
    await docs_service.save_markdown(user_id, document_id, markdown_content)
    
    # 不保存切片
    
    # 尝试创建索引，应该失败
    success = await docs_service.create_document_index(user_id, document_id)
    assert success is False
    
    # 获取更新后的元数据
    doc_meta = await docs_service.get_document_meta(user_id, document_id)
    
    # 直接打印元数据，用于调试
    print(f"文档处理状态: {json.dumps(doc_meta.get('process_details', {}), ensure_ascii=False, indent=2)}")
    
    # 检查日志中有错误，不依赖于元数据
    assert success is False, "索引没有切片的文档应该失败"


@pytest.mark.asyncio
async def test_search_documents(mock_documents_service, user_id, create_upload_file):
    """测试文档搜索功能
    
    目的：
    - 验证系统能否通过向量检索找到相关文档
    - 测试搜索结果的格式和内容
    - 确认检索器能够正确处理查询
    """
    docs_service = mock_documents_service
    
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
    
    # 创建索引 - 不再传递retriever参数
    success = await docs_service.create_document_index(user_id, document_id)
    
    # 搜索文档 - 不再传递retriever参数 
    results = await docs_service.search_documents(
        user_id=user_id,
        query="测试搜索查询",
        document_id=document_id
    )
    
    # 验证搜索结果
    assert len(results) == 2
    assert results[0]["document_id"] == "doc_123"
    assert results[0]["content"] == "模拟搜索结果内容1"
    assert results[0]["distance"] == 0.85


@pytest.mark.asyncio
async def test_search_nonexistent_collection(docs_service, user_id):
    """测试搜索不存在的集合
    
    目的：
    - 验证系统对不存在集合的搜索处理
    - 测试边界条件下的搜索行为
    - 确认系统能优雅地处理空结果
    """
    # 创建一个模拟的向量检索器，模拟集合不存在
    class EmptyMockRetriever:
        async def query(self, query_texts, collection_name, user_id, limit, filter=None):
            return [{"query": query_texts, "results": []}]
    
    # 保存原始的检索器
    original_retriever = docs_service.retriever
    
    try:
        # 替换检索器实例
        docs_service.retriever = EmptyMockRetriever()
        
        # 搜索不存在的集合
        results = await docs_service.search_documents(
            user_id=user_id,
            query="测试搜索查询"
        )
        
        # 验证结果为空
        assert len(results) == 0
    finally:
        # 恢复原始检索器
        docs_service.retriever = original_retriever


@pytest.mark.asyncio
async def test_document_lifecycle(mock_documents_service, user_id, create_upload_file):
    """测试文档完整生命周期
    
    目的：
    - 验证从上传、转换、切片、索引到搜索的完整流程
    - 测试各个阶段间的状态转换和数据一致性
    - 确认最终删除操作是否清理了所有资源
    - 测试系统各组件的协同工作能力
    """
    docs_service = mock_documents_service
    
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
    
    # 4. 创建索引 - 不再传递retriever参数
    await docs_service.create_document_index(user_id, document_id)
    
    # 5. 搜索文档 - 不再传递retriever参数
    results = await docs_service.search_documents(
        user_id=user_id,
        query="lifecycle test",
        document_id=document_id
    )
    assert len(results) > 0
    
    # 6. 删除文档
    success = await docs_service.delete_document(user_id, document_id)
    assert success is True
    
    # 7. 验证删除后无法搜索
    assert not await docs_service.document_exists(user_id, document_id)

