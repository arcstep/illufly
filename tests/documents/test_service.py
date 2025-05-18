import pytest
import asyncio
import tempfile
import os
import json
import aiofiles
from pathlib import Path
from fastapi import UploadFile
from io import BytesIO
from typing import Dict, Any
import time
from unittest.mock import patch

from illufly.llm import LanceRetriever, init_litellm
from illufly.documents.service import DocumentService, Result, ErrorType
from illufly.documents.meta import DocumentMetaManager
from illufly.documents.processor import DocumentProcessor

# 初始化 LiteLLM
cache_dir = os.path.join(os.path.dirname(__file__), "litellm_cache")
os.makedirs(cache_dir, exist_ok=True)
init_litellm(cache_dir)


@pytest.fixture
def temp_dir():
    """创建临时目录用于测试"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def doc_service(temp_dir):
    """创建文档服务实例，使用真实的数据库和处理器"""
    service = DocumentService(
        base_dir=temp_dir,
        max_file_size=5 * 1024 * 1024,  # 5MB限制
        max_total_size_per_user=20 * 1024 * 1024,  # 20MB总限制
        embedding_config={}
    )
    
    return service


@pytest.fixture
def user_id():
    """测试用户ID"""
    return "test_user"


@pytest.fixture
def sample_text_file(temp_dir):
    """创建样本文本文件"""
    file_path = Path(temp_dir) / "sample.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("这是一个测试文本文件\n这是第二行内容\n这是第三行内容")
    return file_path


@pytest.fixture
def upload_file(sample_text_file):
    """创建UploadFile对象"""
    async def _create_upload_file():
        with open(sample_text_file, "rb") as f:
            content = f.read()
            
        # 创建一个能被读取多次的BytesIO对象
        file_like = BytesIO(content)
        
        # 创建UploadFile
        return UploadFile(
            filename="sample.txt",
            file=file_like,
            size=len(content)
        )
    return _create_upload_file


@pytest.mark.asyncio
async def test_create_document(doc_service, user_id):
    """测试创建文档元数据"""
    # 准备测试数据
    doc_info = {
        "document_id": "test_doc_123",
        "original_name": "测试文档.txt",
        "type": "txt",
        "extension": ".txt",
        "source_type": "local",
        "size": 1024
    }
    
    # 创建文档
    result = await doc_service.create_document(user_id, doc_info)
    
    # 验证结果
    assert result.success
    assert result.data["document_id"] == doc_info["document_id"]
    
    # 获取文档并验证
    doc = await doc_service.get_document(user_id, doc_info["document_id"])
    assert doc is not None
    assert doc["document_id"] == doc_info["document_id"]
    assert doc["processed"] == False


@pytest.mark.asyncio
async def test_upload_document(doc_service, user_id, upload_file):
    """测试上传文档"""
    # 上传文件
    file = await upload_file()
    result = await doc_service.upload_document(user_id, file)
    
    # 验证结果
    assert result.success
    assert "document_id" in result.data
    assert result.data["processed"] == False
    
    # 验证文件是否实际保存
    document_id = result.data["document_id"]
    file_path = Path(doc_service.processor.get_document_dir(user_id, document_id)) / result.data["original_name"]
    assert file_path.exists()
    
    # 验证文件内容
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        assert "这是一个测试文本文件" in content


@pytest.mark.asyncio
async def test_create_bookmark(doc_service, user_id):
    """测试创建书签"""
    url = "https://example.com/sample.pdf"
    filename = "示例文档.pdf"
    
    # 创建书签
    result = await doc_service.create_bookmark(user_id, url, filename)
    
    # 验证结果
    assert result.success
    assert "document_id" in result.data
    assert result.data["source_type"] == "remote"
    assert result.data["source_url"] == url
    assert result.data["processed"] == False


@pytest.mark.asyncio
async def test_process_document(doc_service, user_id, upload_file):
    """测试处理文档 - 一体化的转换、切片、嵌入流程"""
    # 上传文件
    file = await upload_file()
    upload_result = await doc_service.upload_document(user_id, file)
    document_id = upload_result.data["document_id"]
    
    # 使用一步式处理文档
    process_result = await doc_service.process_document(user_id, document_id)
    
    # 验证处理结果
    assert process_result.success
    assert process_result.data["document_id"] == document_id
    
    # 验证元数据已更新
    doc = await doc_service.get_document(user_id, document_id)
    assert doc["processed"] == True


@pytest.mark.asyncio
async def test_delete_document(doc_service, user_id, upload_file):
    """测试删除文档"""
    # 上传文件
    file = await upload_file()
    upload_result = await doc_service.upload_document(user_id, file)
    document_id = upload_result.data["document_id"]
    
    # 删除文档
    delete_result = await doc_service.delete_document(user_id, document_id)
    
    # 验证结果
    assert delete_result.success
    assert delete_result.data["deleted"] is True
    assert delete_result.data["document_id"] == document_id
    
    # 验证元数据是否已删除
    doc = await doc_service.get_document(user_id, document_id)
    assert doc is None


@pytest.mark.asyncio
async def test_list_documents(doc_service, user_id, upload_file):
    """测试列出用户文档"""
    # 上传两个文件
    file1 = await upload_file()
    file2 = await upload_file()
    
    await doc_service.upload_document(user_id, file1)
    await doc_service.upload_document(user_id, file2)
    
    # 创建一个书签
    await doc_service.create_bookmark(user_id, "https://example.com/sample.pdf", "示例书签.pdf")
    
    # 列出所有文档
    documents = await doc_service.list_documents(user_id)
    
    # 验证结果
    assert len(documents) == 3
    
    # 验证文档类型
    source_types = [doc.get("source_type") for doc in documents]
    assert source_types.count("local") == 2
    assert source_types.count("remote") == 1


@pytest.mark.asyncio
async def test_invalid_parameters(doc_service, user_id):
    """测试无效参数处理"""
    # 无效文档ID
    result = await doc_service.get_document(user_id, "non_existent_id")
    assert result is None
    
    # 测试无效文档ID的处理操作
    invalid_id = "non_existent_doc"
    process_result = await doc_service.process_document(user_id, invalid_id)
    assert not process_result.success
    assert process_result.error_type == ErrorType.RESOURCE_ERROR


@pytest.mark.asyncio
async def test_search_chunks(doc_service, user_id, upload_file):
    """测试搜索文档内容"""
    # 上传文件
    file = await upload_file()
    upload_result = await doc_service.upload_document(user_id, file)
    document_id = upload_result.data["document_id"]
    
    # 处理文档（这将执行嵌入）
    await doc_service.process_document(user_id, document_id)
    
    # 搜索文档
    search_result = await doc_service.search_chunks(user_id, "测试文本", document_id)
    
    # 验证结果结构
    assert search_result.success
    assert "chunks" in search_result.data
    
    # 由于是测试环境，可能没有实际的嵌入结果，验证结构即可


@pytest.mark.asyncio
async def test_update_document_metadata(doc_service, user_id, upload_file):
    """测试更新文档元数据"""
    # 上传文件
    file = await upload_file()
    upload_result = await doc_service.upload_document(user_id, file)
    document_id = upload_result.data["document_id"]
    
    # 更新元数据
    new_title = "更新后的标题"
    new_tags = ["标签1", "标签2"]
    update_result = await doc_service.update_document_metadata(
        user_id, 
        document_id,
        title=new_title,
        tags=new_tags
    )
    
    # 验证结果
    assert update_result.success
    assert update_result.data["title"] == new_title
    assert update_result.data["tags"] == new_tags
    
    # 获取文档并再次验证
    doc = await doc_service.get_document(user_id, document_id)
    assert doc["title"] == new_title
    assert doc["tags"] == new_tags


@pytest.mark.asyncio
async def test_list_processed_documents(doc_service, user_id, upload_file):
    """测试列出已处理/未处理的文档"""
    # 上传两个文件
    file1 = await upload_file()
    file2 = await upload_file()
    
    upload_result1 = await doc_service.upload_document(user_id, file1)
    upload_result2 = await doc_service.upload_document(user_id, file2)
    
    # 处理第一个文档
    await doc_service.process_document(user_id, upload_result1.data["document_id"])
    
    # 列出已处理的文档
    processed_docs = await doc_service.list_processed_documents(user_id, processed=True)
    
    # 验证结果
    assert len(processed_docs) == 1
    assert processed_docs[0]["document_id"] == upload_result1.data["document_id"]
    
    # 列出未处理的文档
    unprocessed_docs = await doc_service.list_processed_documents(user_id, processed=False)
    
    # 验证结果
    assert len(unprocessed_docs) == 1
    assert unprocessed_docs[0]["document_id"] == upload_result2.data["document_id"]


@pytest.fixture(scope="function", autouse=True)
async def cleanup_async_tasks():
    yield
    # 等待所有挂起的任务完成
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)