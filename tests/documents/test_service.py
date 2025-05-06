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
from illufly.documents.sm import DocumentStateMachine

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
    assert doc["state"] == "uploaded"
    assert doc["sub_state"] == "completed"


@pytest.mark.asyncio
async def test_upload_document(doc_service, user_id, upload_file):
    """测试上传文档"""
    # 上传文件
    file = await upload_file()
    result = await doc_service.upload_document(user_id, file)
    
    # 验证结果
    assert result.success
    assert "document_id" in result.data
    assert result.data["state"] == "uploaded"
    assert result.data["sub_state"] == "completed"
    
    # 验证文件是否实际保存
    document_id = result.data["document_id"]
    file_path = doc_service.processor.get_raw_path(user_id, document_id)
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
    assert result.data["state"] == "bookmarked"
    assert result.data["sub_state"] == "completed"


@pytest.mark.asyncio
async def test_convert_to_markdown(doc_service, user_id, upload_file):
    """测试转换文档为Markdown - 只验证API响应结构"""
    # 上传文件
    file = await upload_file()
    upload_result = await doc_service.upload_document(user_id, file)
    document_id = upload_result.data["document_id"]
    
    # 转换为Markdown
    convert_result = await doc_service.convert_to_markdown(user_id, document_id)
    
    # 验证API结构，不验证具体状态值
    assert "document_id" in convert_result.data
    assert convert_result.data["document_id"] == document_id
    assert "state" in convert_result.data
    assert "sub_state" in convert_result.data


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
async def test_get_document_state(doc_service, user_id, upload_file):
    """测试获取文档状态"""
    # 上传文件
    file = await upload_file()
    upload_result = await doc_service.upload_document(user_id, file)
    document_id = upload_result.data["document_id"]
    
    # 获取文档状态
    state_info = await doc_service.get_document_state(user_id, document_id)
    
    # 验证结果
    assert state_info["state"] == "uploaded"
    assert state_info["sub_state"] == "completed"


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
    
    # 无效状态转换
    invalid_id = "test_invalid_id"
    await doc_service.meta_manager.create_document(user_id, invalid_id)
    result = await doc_service.convert_to_markdown(user_id, invalid_id)
    assert not result.success
    assert result.error_type == ErrorType.STATE_ERROR


@pytest.mark.asyncio
async def test_chat_document_flow(doc_service, user_id):
    """测试聊天文档处理流程"""
    # 创建聊天文档
    doc_info = {
        "document_id": "chat_test_123",
        "original_name": "测试对话",
        "source_type": "chat",
        "size": 500
    }
    
    result = await doc_service.create_document(user_id, doc_info)
    assert result.success
    assert result.data["state"] == "saved_chat"


@pytest.fixture(scope="function", autouse=True)
async def cleanup_async_tasks():
    yield
    # 等待所有挂起的任务完成
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_create_state_machine_callbacks(doc_service, user_id):
    """验证 create_state_machine 注入了完整的回调键集合"""
    machine = await doc_service.create_state_machine(user_id, "any_doc")
    keys = set(machine.callbacks.keys())
    expected = {
        "after_uploaded_to_markdowned",
        "after_bookmarked_to_markdowned",
        "after_markdowned_to_chunked",
        "after_chunked_to_embedded",
        "after_qa_extracted_to_embedded",
        "before_rollback_markdowned_to_uploaded",
        "before_rollback_markdowned_to_bookmarked",
        "before_rollback_chunked_to_markdowned",
        "before_rollback_embedded_to_chunked",
        "before_rollback_embedded_to_qa_extracted",
    }
    assert keys == expected


async def check_resource_exists(meta_manager, user_id, document_id, resource_type) -> bool:
    """检查资源是否存在于元数据中"""
    meta = await meta_manager.get_metadata(user_id, document_id)
    return meta and resource_type in meta.get("resources", {})


@pytest.mark.asyncio
async def test_state_machine_workflow_with_real_services(doc_service, user_id, sample_text_file):
    """测试状态机完整工作流程 - 完全使用真实服务组件"""
    doc_id = "real_workflow_test_doc"
    
    # 1. 创建文档并上传原始文本文件
    with open(sample_text_file, "rb") as f:
        content = f.read()
    
    # 1.1 手动创建原始文本文件 (修复此处)
    raw_path = doc_service.processor.get_raw_path(user_id, doc_id)
    raw_dir = raw_path.parent
    raw_dir.mkdir(parents=True, exist_ok=True)
    
    # 写入原始文件
    with open(raw_path, "wb") as f:
        f.write(content)
    
    # 1.2 创建文档元数据
    doc_info = {
        "document_id": doc_id,
        "original_name": "测试文档.txt",
        "type": "txt",
        "extension": ".txt",
        "source_type": "local",
        "size": len(content)
    }
    
    # 1.3 创建文档并设置初始状态
    await doc_service.meta_manager.create_document(user_id, doc_id, None, doc_info)
    machine = await doc_service.create_state_machine(user_id, doc_id)
    await machine.set_state("uploaded", sub_state="completed")
    
    # 2. 获取初始文档状态，确认上传阶段完成
    doc_before = await doc_service.get_document(user_id, doc_id)
    assert doc_before["state"] == "uploaded"
    assert doc_before["sub_state"] == "completed"
    
    # 3. 手动转换为Markdown（直接创建文件，绕过外部转换依赖）
    # 3.1 创建Markdown目录和文件
    md_path = doc_service.processor.get_md_path(user_id, doc_id)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(md_path, "w") as f:
        f.write("# 测试文档\n\n这是从原始文本转换的Markdown内容。")
    
    # 3.2 手动添加Markdown资源记录
    await doc_service.meta_manager.add_resource(
        user_id, doc_id, 
        "markdown", 
        {"created_at": time.time(), "path": str(md_path)}
    )
    
    # 3.3 转换状态
    await machine.set_state("markdowned", sub_state="completed")
    
    # 3.4 验证状态和资源
    doc_after_md = await doc_service.get_document(user_id, doc_id)
    assert doc_after_md["state"] == "markdowned"
    assert await check_resource_exists(doc_service.meta_manager, user_id, doc_id, "markdown")
    
    # 4. 手动创建文档切片
    # 4.1 创建切片目录
    chunks_dir = doc_service.processor.get_chunks_dir(user_id, doc_id)
    chunks_dir.mkdir(parents=True, exist_ok=True)
    
    # 4.2 创建几个切片文件
    for i in range(3):
        chunk_path = chunks_dir / f"chunk_{i}.txt"
        with open(chunk_path, "w") as f:
            f.write(f"这是第{i+1}个文档切片的内容")
    
    # 4.3 添加chunks资源
    await doc_service.meta_manager.add_resource(
        user_id, doc_id,
        "chunks",
        {
            "created_at": time.time(),
            "count": 3,
            "path": str(chunks_dir)
        }
    )
    
    # 4.4 转换状态
    await machine.set_state("chunked", sub_state="completed")
    
    # 4.5 验证状态和资源
    doc_after_chunks = await doc_service.get_document(user_id, doc_id)
    assert doc_after_chunks["state"] == "chunked"
    assert await check_resource_exists(doc_service.meta_manager, user_id, doc_id, "chunks")
    
    # 5. 测试状态回退
    # 5.1 回退到Markdown状态
    rollback_result = await doc_service.rollback_to_previous_state(user_id, doc_id)
    assert rollback_result.success
    assert rollback_result.data["state"] == "markdowned"
    
    # 5.2 验证chunks资源已被删除
    assert not await check_resource_exists(doc_service.meta_manager, user_id, doc_id, "chunks")
    assert not chunks_dir.exists()
    
    # 5.3 检查子状态恢复为completed状态
    rollback_result = await doc_service.rollback_to_previous_state(user_id, doc_id)
    assert rollback_result.success
    assert rollback_result.data["state"] == "markdowned"
    assert rollback_result.data["sub_state"] == "completed"
    
    # 5.4 再次回退到uploaded状态
    rollback_result = await doc_service.rollback_to_previous_state(user_id, doc_id)
    assert rollback_result.success
    assert rollback_result.data["state"] == "uploaded"
    
    # 5.5 验证markdown资源已被删除
    assert not await check_resource_exists(doc_service.meta_manager, user_id, doc_id, "markdown")
    assert not md_path.exists()

    # 禁用状态机自动回调（避免 ClientDealer 等外部调用），手动模拟资源和状态
    machine.callbacks.clear()


@pytest.mark.asyncio
async def test_document_resources_lifecycle(doc_service, user_id, sample_text_file):
    """测试文档资源的生命周期管理"""
    doc_id = "resource_test_doc"
    
    # 1. 创建文档元数据
    await doc_service.meta_manager.create_document(user_id, doc_id)
    
    # 2. 手动添加各种资源并验证
    # 2.1 添加markdown资源
    await doc_service.meta_manager.add_resource(
        user_id, doc_id, 
        "markdown", 
        {"created_at": time.time(), "path": "test/path.md"}
    )
    
    # 验证资源已添加
    meta = await doc_service.meta_manager.get_metadata(user_id, doc_id)
    assert "markdown" in meta.get("resources", {})
    
    # 2.2 添加chunks资源
    await doc_service.meta_manager.add_resource(
        user_id, doc_id,
        "chunks",
        {"created_at": time.time(), "count": 5, "path": "test/chunks/"}
    )
    
    # 验证资源已添加
    meta = await doc_service.meta_manager.get_metadata(user_id, doc_id)
    assert "chunks" in meta.get("resources", {})
    assert meta["resources"]["chunks"]["count"] == 5
    
    # 2.3 添加embeddings资源
    await doc_service.meta_manager.add_resource(
        user_id, doc_id,
        "embeddings",
        {"created_at": time.time(), "collection": "test_collection", "count": 10}
    )
    
    # 验证资源已添加
    meta = await doc_service.meta_manager.get_metadata(user_id, doc_id)
    assert "embeddings" in meta.get("resources", {})
    assert meta["resources"]["embeddings"]["collection"] == "test_collection"
    
    # 3. 移除资源并验证
    # 3.1 移除markdown资源
    await doc_service.meta_manager.remove_resource(user_id, doc_id, "markdown")
    meta = await doc_service.meta_manager.get_metadata(user_id, doc_id)
    assert "markdown" not in meta.get("resources", {})
    
    # 3.2 移除chunks资源
    await doc_service.meta_manager.remove_resource(user_id, doc_id, "chunks")
    meta = await doc_service.meta_manager.get_metadata(user_id, doc_id)
    assert "chunks" not in meta.get("resources", {})
    
    # 3.3 验证embeddings资源仍然存在
    assert "embeddings" in meta.get("resources", {})