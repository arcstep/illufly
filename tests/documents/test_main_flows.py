# tests/documents/test_main_flows.py

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
from unittest.mock import patch, MagicMock

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
def sample_markdown_file(temp_dir):
    """创建样本Markdown文件"""
    file_path = Path(temp_dir) / "sample.md"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("# 这是一个Markdown文件\n\n## 第一部分\n这是第一部分的内容\n\n## 第二部分\n这是第二部分的内容")
    return file_path


@pytest.fixture
def sample_pdf_file(temp_dir):
    """创建模拟的PDF文件（实际是一个文本文件，但有pdf扩展名）"""
    file_path = Path(temp_dir) / "sample.pdf"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("这是一个模拟的PDF文件内容")
    return file_path


@pytest.fixture
def sample_docx_file(temp_dir):
    """创建模拟的DOCX文件（实际是一个文本文件，但有docx扩展名）"""
    file_path = Path(temp_dir) / "sample.docx"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("这是一个模拟的DOCX文件内容")
    return file_path


@pytest.fixture
def create_upload_file():
    """创建可重用的上传文件生成器"""
    async def _create_file(file_path, filename=None):
        with open(file_path, "rb") as f:
            content = f.read()
            
        # 创建一个能被读取多次的BytesIO对象
        file_like = BytesIO(content)
        
        # 如果没有指定文件名，使用原始文件名
        if not filename:
            filename = Path(file_path).name
        
        # 创建UploadFile
        return UploadFile(
            filename=filename,
            file=file_like,
            size=len(content)
        )
    return _create_file


@pytest.mark.asyncio
async def test_pdf_document_processing(doc_service, user_id, sample_pdf_file, create_upload_file):
    """测试上传PDF文件并处理（需要转换流程）"""
    # 模拟转换成功的结果
    mock_conversion_result = {
        "success": True,
        "content": "# 转换后的PDF内容\n\n这是从PDF转换的内容，包含一些文本。",
        "content_preview": "# 转换后的PDF内容",
        "method": "conversion"
    }
    
    # 上传PDF文件
    file = await create_upload_file(sample_pdf_file)
    
    # 使用补丁替换PDF转换方法
    with patch.object(doc_service.processor, 'convert_to_markdown', 
                      return_value=mock_conversion_result):
        # 上传并立即处理
        result = await doc_service.upload_document(
            user_id, file, auto_process=True
        )
        
        # 验证上传成功
        assert result.success
        assert result.data["processed"] == True
        assert result.data["type"] == "pdf"
        
        # 验证文件已保存
        document_id = result.data["document_id"]
        
        # 验证上传的原始文件存在
        file_path = Path(doc_service.processor.get_document_dir(user_id, document_id)) / result.data["original_name"]
        assert file_path.exists()


@pytest.mark.asyncio
async def test_docx_document_processing(doc_service, user_id, sample_docx_file, create_upload_file):
    """测试上传DOCX文件并处理（需要转换流程）"""
    # 模拟转换成功的结果
    mock_conversion_result = {
        "success": True,
        "content": "# 转换后的DOCX内容\n\n这是从DOCX转换的内容，包含一些文本。",
        "content_preview": "# 转换后的DOCX内容",
        "method": "conversion"
    }
    
    # 上传DOCX文件
    file = await create_upload_file(sample_docx_file)
    
    # 使用补丁替换DOCX转换方法
    with patch.object(doc_service.processor, 'convert_to_markdown', 
                      return_value=mock_conversion_result):
        # 上传并不自动处理
        upload_result = await doc_service.upload_document(user_id, file)
        document_id = upload_result.data["document_id"]
        
        # 验证初始状态为未处理
        assert upload_result.data["processed"] == False
        
        # 手动触发处理
        process_result = await doc_service.process_document(user_id, document_id)
        
        # 验证处理完成
        assert process_result.success
        
        # 检查文档状态已更新
        doc = await doc_service.get_document(user_id, document_id)
        assert doc["processed"] == True
        assert doc["type"] == "docx"


@pytest.mark.asyncio
async def test_markdown_document_processing(doc_service, user_id, sample_markdown_file, create_upload_file):
    """测试上传Markdown文件并处理（无需转换流程）"""
    # 上传Markdown文件
    file = await create_upload_file(sample_markdown_file)
    
    # 上传并处理
    result = await doc_service.upload_document(
        user_id, file, auto_process=True
    )
    
    # 验证上传和处理成功
    assert result.success
    assert result.data["processed"] == True
    assert result.data["type"] == "md"
    
    # 验证文件存在
    document_id = result.data["document_id"]
    file_path = Path(doc_service.processor.get_document_dir(user_id, document_id)) / result.data["original_name"]
    assert file_path.exists()


@pytest.mark.asyncio
async def test_remote_pdf_document_processing(doc_service, user_id):
    """测试远程PDF文档处理"""
    # 远程PDF URL
    url = "https://example.com/sample.pdf"
    filename = "远程PDF文档.pdf"
    
    # 模拟转换成功的结果
    mock_conversion_result = {
        "success": True,
        "content": "# 远程PDF文档内容\n\n这是远程PDF文档的转换内容。",
        "content_preview": "# 远程PDF文档内容",
        "method": "conversion"
    }
    
    # 使用补丁替换转换方法
    with patch.object(doc_service.processor, 'convert_to_markdown', 
                      return_value=mock_conversion_result):
        # 创建书签并处理
        result = await doc_service.create_bookmark(
            user_id, url, filename, auto_process=True
        )
        
        # 验证创建和处理成功
        assert result.success
        assert result.data["processed"] == True
        assert result.data["source_type"] == "remote"
        assert result.data["source_url"] == url
        assert result.data["type"] == "pdf"


@pytest.mark.asyncio
async def test_remote_markdown_document_processing(doc_service, user_id):
    """测试远程Markdown文档处理"""
    # 远程Markdown URL
    url = "https://example.com/sample.md"
    filename = "远程Markdown文档.md"
    
    # 模拟直接读取方法的结果
    mock_content = "# 远程Markdown文档\n\n这是直接读取的远程Markdown内容。"
    mock_result = {
        "success": True,
        "content": mock_content,
        "content_preview": "# 远程Markdown文档",
        "method": "direct_read"
    }
    
    # 使用补丁替换方法
    with patch.object(doc_service.processor, 'convert_to_markdown', 
                      return_value=mock_result):
        # 创建书签并处理
        result = await doc_service.create_bookmark(
            user_id, url, filename, auto_process=True
        )
        
        # 验证创建和处理成功
        assert result.success
        assert result.data["processed"] == True
        assert result.data["source_type"] == "remote"
        assert result.data["source_url"] == url
        assert result.data["type"] == "md"


@pytest.mark.asyncio
async def test_duplicate_document_upload(doc_service, user_id, sample_text_file, create_upload_file):
    """测试重复上传相同文件的情况"""
    # 第一次上传
    file1 = await create_upload_file(sample_text_file)
    result1 = await doc_service.upload_document(user_id, file1)
    document_id1 = result1.data["document_id"]
    
    # 第二次上传相同的文件
    file2 = await create_upload_file(sample_text_file)
    result2 = await doc_service.upload_document(user_id, file2)
    document_id2 = result2.data["document_id"]
    
    # 验证两次上传得到了不同的文档ID
    assert document_id1 != document_id2
    
    # 验证两个文档都存在
    doc1 = await doc_service.get_document(user_id, document_id1)
    doc2 = await doc_service.get_document(user_id, document_id2)
    assert doc1 is not None
    assert doc2 is not None


@pytest.mark.asyncio
async def test_duplicate_bookmark_creation(doc_service, user_id):
    """测试重复创建相同URL的书签情况"""
    # 相同的URL和文件名
    url = "https://example.com/duplicate_test.pdf"
    filename = "重复测试.pdf"
    
    # 第一次创建书签
    result1 = await doc_service.create_bookmark(user_id, url, filename)
    document_id1 = result1.data["document_id"]
    
    # 第二次创建相同URL的书签
    result2 = await doc_service.create_bookmark(user_id, url, filename)
    document_id2 = result2.data["document_id"]
    
    # 验证得到不同的文档ID
    assert document_id1 != document_id2
    
    # 验证两个文档都存在
    doc1 = await doc_service.get_document(user_id, document_id1)
    doc2 = await doc_service.get_document(user_id, document_id2)
    assert doc1 is not None
    assert doc2 is not None


@pytest.mark.asyncio
async def test_failed_processing_retry(doc_service, user_id, sample_pdf_file, create_upload_file):
    """测试处理失败后的重试机制"""
    # 上传PDF文件
    file = await create_upload_file(sample_pdf_file)
    upload_result = await doc_service.upload_document(user_id, file)
    document_id = upload_result.data["document_id"]
    
    # 模拟处理失败
    with patch.object(doc_service.processor, 'process_document_complete', 
                      side_effect=ValueError("模拟处理失败")):
        # 尝试处理文档
        process_result = await doc_service.process_document(user_id, document_id)
        
        # 验证处理失败
        assert not process_result.success
        assert process_result.error_type == ErrorType.VALIDATION_ERROR
        
        # 验证文档标记为未处理
        doc = await doc_service.get_document(user_id, document_id)
        assert doc["processed"] == False
    
    # 模拟处理成功的结果
    mock_success_result = {
        "document_id": document_id,
        "collection": f"user_{user_id}",
        "chunks_count": 3,
        "vectors_count": 3,
        "success": True
    }
    
    # 重试处理，这次成功
    with patch.object(doc_service.processor, 'process_document_complete', 
                      return_value=mock_success_result):
        # 重试处理
        retry_result = await doc_service.process_document(user_id, document_id)
        
        # 验证处理成功
        assert retry_result.success
        
        # 验证文档已更新
        doc = await doc_service.get_document(user_id, document_id)
        assert doc["processed"] == True


@pytest.mark.asyncio
async def test_document_overwrite(doc_service, user_id, sample_text_file, create_upload_file):
    """测试使用相同ID覆盖文档"""
    # 固定的文档ID
    fixed_id = "fixed_doc_id"
    
    # 创建第一个文档
    file1 = await create_upload_file(sample_text_file, "第一个文档.txt")
    
    # 为了使用固定ID，我们需要修改内部实现
    with patch.object(doc_service.processor, 'generate_document_id', return_value=fixed_id):
        # 上传第一个文档
        result1 = await doc_service.upload_document(user_id, file1)
        assert result1.success
        assert result1.data["document_id"] == fixed_id
        
        # 验证文档存在
        doc1 = await doc_service.get_document(user_id, fixed_id)
        assert doc1["original_name"] == "第一个文档.txt"
        
        # 删除该文档
        delete_result = await doc_service.delete_document(user_id, fixed_id)
        assert delete_result.success
        
        # 创建第二个文档，使用相同ID
        file2 = await create_upload_file(sample_text_file, "第二个文档.txt")
        result2 = await doc_service.upload_document(user_id, file2)
        
        # 验证使用相同ID成功创建
        assert result2.success
        assert result2.data["document_id"] == fixed_id
        
        # 验证是新文档
        doc2 = await doc_service.get_document(user_id, fixed_id)
        assert doc2["original_name"] == "第二个文档.txt"


@pytest.fixture(scope="function", autouse=True)
async def cleanup_async_tasks():
    yield
    # 等待所有挂起的任务完成
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
