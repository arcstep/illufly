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

# --------- 辅助函数和夹具 ---------

@pytest.fixture
def user_id():
    """测试用户ID"""
    return "test_user_123"

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


# --------- 测试用例 ---------

@pytest.mark.asyncio
async def test_document_state_machine_transitions(docs_service, user_id, create_upload_file):
    """测试文档状态机的状态转换
    
    目的：
    - 验证状态机的所有合法状态转换
    - 测试每个转换对文档元数据的影响
    - 确认状态转换过程中的回调函数正常工作
    - 验证状态机是否正确维护文档状态
    """
    # 创建文档
    file = create_upload_file(filename="state_test.pdf", content=b"state machine test")
    doc_meta = await docs_service.save_document(user_id, file)
    document_id = doc_meta["document_id"]
    
    # 获取状态机实例
    machine = await docs_service.get_document_machine(user_id, document_id)
    
    # 验证初始状态
    assert machine.current_state.id == 'uploaded'
    
    # 测试状态转换: uploaded -> markdowning
    await machine.start_markdown_from_upload()
    doc_meta = await docs_service.get_document_meta(user_id, document_id)
    assert doc_meta["state"] == "markdowning"
    
    # 模拟Markdown转换完成
    await machine.complete_markdown()
    doc_meta = await docs_service.get_document_meta(user_id, document_id)
    assert doc_meta["state"] == "markdowned"
    assert doc_meta.get("has_markdown") is True
    
    # 测试状态转换: markdowned -> chunking
    await machine.start_chunking()
    doc_meta = await docs_service.get_document_meta(user_id, document_id)
    assert doc_meta["state"] == "chunking"
    
    # 模拟切片完成
    await machine.complete_chunking(chunks_count=5, avg_length=200)
    doc_meta = await docs_service.get_document_meta(user_id, document_id)
    assert doc_meta["state"] == "chunked"
    assert doc_meta.get("has_chunks") is True
    
    # 测试状态转换: chunked -> embedding
    await machine.start_embedding_from_chunks()
    doc_meta = await docs_service.get_document_meta(user_id, document_id)
    assert doc_meta["state"] == "embedding"
    
    # 模拟嵌入完成
    await machine.complete_embedding(indexed_chunks=5)
    doc_meta = await docs_service.get_document_meta(user_id, document_id)
    assert doc_meta["state"] == "embedded"
    assert doc_meta.get("has_embeddings") is True

@pytest.mark.asyncio
async def test_document_state_machine_error_handling(docs_service, user_id, create_upload_file):
    """测试状态机的错误处理能力
    
    目的：
    - 验证状态机能否正确处理处理过程中的错误
    - 测试错误状态的记录和元数据更新
    - 确认从失败状态恢复到就绪状态的能力
    - 验证错误信息的记录和检索
    """
    # 创建文档
    file = create_upload_file(filename="error_test.pdf", content=b"error handling test")
    doc_meta = await docs_service.save_document(user_id, file)
    document_id = doc_meta["document_id"]
    
    # 获取状态机实例
    machine = await docs_service.get_document_machine(user_id, document_id)
    
    # 开始Markdown转换
    await machine.start_markdown_from_upload()
    
    # 模拟错误
    await machine.fail_markdown(error="测试错误：Markdown转换失败")
    
    # 验证错误状态
    doc_meta = await docs_service.get_document_meta(user_id, document_id)
    assert doc_meta["state"] == "markdown_failed"
    
    # 测试从失败状态恢复
    await machine.retry_markdown_from_failed()
    doc_meta = await docs_service.get_document_meta(user_id, document_id)
    assert doc_meta["state"] == "markdowning"

@pytest.mark.asyncio
async def test_invalid_state_transitions(docs_service, user_id, create_upload_file):
    """测试无效的状态转换处理
    
    目的：
    - 验证状态机能否正确拒绝非法的状态转换
    - 测试状态转换失败时的异常处理
    - 确认状态机对状态流程的强制约束
    - 验证合法转换序列的正确性
    """
    # 创建文档
    file = create_upload_file(filename="invalid_state.pdf", content=b"invalid transition test")
    doc_meta = await docs_service.save_document(user_id, file)
    document_id = doc_meta["document_id"]
    
    # 获取状态机实例
    machine = await docs_service.get_document_machine(user_id, document_id)
    
    # 尝试无效转换：直接从ready到chunking（应该失败）
    with pytest.raises(Exception):  # 应该引发状态转换异常
        await machine.start_chunking()
    
    # 验证状态未变
    doc_meta = await docs_service.get_document_meta(user_id, document_id)
    assert doc_meta["state"] == "uploaded"
    
    # 有效转换序列
    await machine.start_markdown_from_upload()
    await machine.complete_markdown()
    
    # 现在可以开始chunking
    await machine.start_chunking()
    doc_meta = await docs_service.get_document_meta(user_id, document_id)
    assert doc_meta["state"] == "chunking"

@pytest.mark.asyncio
async def test_save_markdown_with_state_machine(docs_service, user_id, create_upload_file):
    """测试使用状态机进行Markdown保存
    
    目的：
    - 验证save_markdown方法对状态机的正确使用
    - 测试Markdown内容更新时的状态处理
    - 确认重复保存Markdown时的状态一致性
    - 验证Markdown转换功能与状态机的集成
    """
    # 创建文档
    file = create_upload_file(filename="markdown_test.pdf", content=b"markdown test content")
    doc_meta = await docs_service.save_document(user_id, file)
    document_id = doc_meta["document_id"]
    
    # 保存Markdown内容 - 这应该触发状态机转换
    markdown_content = "# Test Document\nThis is a test markdown"
    updated_meta = await docs_service.save_markdown(user_id, document_id, markdown_content)
    
    # 验证状态
    assert updated_meta["state"] == "markdowned"
    assert updated_meta.get("has_markdown") is True
    
    # 尝试再次保存Markdown - 应通过状态机处理
    updated_markdown = "# Updated Document\nThis content was changed"
    updated_meta2 = await docs_service.save_markdown(user_id, document_id, updated_markdown)
    
    # 验证状态保持markdowned
    assert updated_meta2["state"] == "markdowned"
    
    # 验证内容已更新
    retrieved_markdown = await docs_service.get_markdown(user_id, document_id)
    assert retrieved_markdown == updated_markdown

@pytest.mark.asyncio
async def test_save_chunks_with_state_machine(docs_service, user_id, create_upload_file):
    """测试使用状态机进行文档切片
    
    目的：
    - 验证save_chunks方法对状态机的正确使用
    - 测试文档切片过程中的状态转换
    - 确认切片元数据的正确记录
    - 验证切片功能与状态机的集成
    """
    # 创建文档并转换为Markdown
    file = create_upload_file(filename="chunks_test.pdf", content=b"chunks test content")
    doc_meta = await docs_service.save_document(user_id, file)
    document_id = doc_meta["document_id"]
    await docs_service.save_markdown(user_id, document_id, "# Test Document\nChunks test markdown")
    
    # 创建测试切片
    chunks = [
        {"content": "Chunk 1 content", "metadata": {"page": 1}},
        {"content": "Chunk 2 content", "metadata": {"page": 1}}
    ]
    
    # 保存切片 - 应触发状态机转换
    success = await docs_service.save_chunks(user_id, document_id, chunks)
    assert success is True
    
    # 验证状态
    doc_meta = await docs_service.get_document_meta(user_id, document_id)
    assert doc_meta["state"] == "chunked"
    assert doc_meta.get("has_chunks") is True
    
    # 验证元数据包含切片统计信息
    assert "chunks" in doc_meta
    assert len(doc_meta["chunks"]) == 2
    assert "chunking" in doc_meta["process_details"]
    assert doc_meta["process_details"]["chunking"]["success"] is True

@pytest.mark.asyncio
async def test_chat_document_qa_extraction(docs_service, user_id):
    """测试从对话记录提取QA对"""
    # 创建对话文档
    doc_meta = await docs_service.create_chat_document(
        user_id=user_id,
        chat_id="chat123",
        title="测试对话"
    )
    document_id = doc_meta["document_id"]
    
    # 获取状态机实例
    machine = await docs_service.get_document_machine(user_id, document_id)
    
    # 验证已激活为saved_chat状态
    assert machine.current_state.id == 'saved_chat'
    
    # 测试QA提取
    await machine.start_qa_extraction()
    doc_meta = await docs_service.get_document_meta(user_id, document_id)
    assert doc_meta["state"] == "qa_extracting"
    
    # 模拟QA提取完成
    qa_pairs = [
        {"question": "问题1", "answer": "回答1"},
        {"question": "问题2", "answer": "回答2"}
    ]
    success = await docs_service.save_qa_pairs(user_id, document_id, qa_pairs)
    assert success is True
    
    # 验证状态
    doc_meta = await docs_service.get_document_meta(user_id, document_id)
    assert doc_meta["state"] == "qa_extracted"
    assert doc_meta.get("has_qa_pairs") is True
    
    # 重新获取状态机实例以确保状态同步
    machine = await docs_service.get_document_machine(user_id, document_id)
    
    # 测试从QA对到向量化
    await machine.start_embedding_from_qa()
    doc_meta = await docs_service.get_document_meta(user_id, document_id)
    assert doc_meta["state"] == "embedding"

@pytest.mark.asyncio
async def test_bookmark_document_processing(docs_service, user_id):
    """测试网络书签文档处理"""
    # 创建书签文档
    doc_meta = await docs_service.create_bookmark_document(
        user_id=user_id,
        url="https://example.com",
        title="测试网页"
    )
    document_id = doc_meta["document_id"]
    
    # 获取状态机实例
    machine = await docs_service.get_document_machine(user_id, document_id)
    
    # 验证初始状态
    assert machine.current_state.id == 'bookmarked'
    
    # 测试状态转换: bookmarked -> markdowning
    await machine.start_markdown_from_bookmark()
    doc_meta = await docs_service.get_document_meta(user_id, document_id)
    assert doc_meta["state"] == "markdowning"
    
    # 其他处理流程与本地文档相同...

@pytest.mark.asyncio
async def test_machine_helper_methods(docs_service, user_id, create_upload_file):
    """测试状态机辅助方法"""
    # 创建文档
    file = create_upload_file(filename="helper_test.pdf", content=b"helper methods test")
    doc_meta = await docs_service.save_document(user_id, file)
    document_id = doc_meta["document_id"]
    
    # 获取状态机实例
    machine = await docs_service.get_document_machine(user_id, document_id)
    
    # 初始状态检查
    assert machine.has_markdown() is False
    assert machine.has_chunks() is False
    assert machine.has_qa_pairs() is False
    assert machine.has_embeddings() is False
    assert machine.get_source_type() == "local"
    assert machine.is_processing() is False
    assert machine.has_failed() is False
    
    # 完成Markdown处理
    await machine.start_markdown_from_upload()
    await machine.complete_markdown()
    
    # 检查状态
    assert machine.has_markdown() is True
    assert machine.has_chunks() is False
    
    # 完成切片
    await machine.start_chunking()
    await machine.complete_chunking(chunks_count=5)
    
    # 检查状态
    assert machine.has_chunks() is True
    assert machine.has_embeddings() is False
    
    # 开始向量化
    await machine.start_embedding_from_chunks()
    assert machine.is_processing() is True
    
    # 完成向量化
    await machine.complete_embedding(indexed_chunks=5)
    assert machine.has_embeddings() is True
    assert machine.is_processing() is False
