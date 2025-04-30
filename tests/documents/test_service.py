import pytest
import asyncio
import tempfile
import os
import json
import aiofiles
from pathlib import Path
from fastapi import UploadFile
from io import BytesIO

from illufly.llm import LanceRetriever, init_litellm
from illufly.documents.service import DocumentService, Result, ErrorType
from illufly.documents.meta import DocumentMetaManager
from illufly.documents.processor import DocumentProcessor
from illufly.documents.sm import DocumentStateMachine
from voidring import IndexedRocksDB

# 初始化 LiteLLM
cache_dir = os.path.join(os.path.dirname(__file__), "litellm_cache")
os.makedirs(cache_dir, exist_ok=True)
init_litellm(cache_dir)


class SimpleVoidrailClient:
    """简单的文档转换客户端真实实现"""
    
    async def stream(self, task=None, file_path=None, **kwargs):
        """流式返回处理结果"""
        if task != "file_to_markdown":
            raise ValueError(f"不支持的任务类型: {task}")
            
        # 从文件读取内容并转换为简单的Markdown
        if file_path and os.path.exists(file_path):
            file_name = os.path.basename(file_path)
            file_ext = os.path.splitext(file_name)[1].lower()
            
            # 简单模拟不同文件类型的转换
            content = f"# {file_name}\n\n"
            
            if file_ext == '.txt':
                # 文本文件直接读取内容
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read(2000)  # 读取最多2000字符
                content += text
            elif file_ext == '.pdf':
                content += "这是从PDF文件中提取的文本内容。\n\n* 第一段落\n* 第二段落\n* 第三段落"
            elif file_ext in ['.jpg', '.jpeg', '.png', '.gif']:
                content += "这是图片描述文本。\n\n图片中可能包含的内容..."
            else:
                content += "这是通用文档内容。\n\n## 第一章\n\n这是第一章的内容。\n\n## 第二章\n\n这是第二章的内容。"
                
            # 流式返回
            yield content


# 简单的IndexedRocksDB模拟
class SimpleIndexedRocksDB:
    def __init__(self, db_path):
        self.db_path = db_path
        self.storage = {}
        os.makedirs(db_path, exist_ok=True)
    
    async def get(self, collection, key):
        if collection not in self.storage:
            return None
        return self.storage[collection].get(key)
    
    async def put(self, collection, key, value):
        if collection not in self.storage:
            self.storage[collection] = {}
        self.storage[collection][key] = value
        return True
    
    async def delete(self, collection, key):
        if collection in self.storage and key in self.storage[collection]:
            del self.storage[collection][key]
            return True
        return False
    
    async def scan(self, collection, prefix=None):
        if collection not in self.storage:
            return []
        if prefix:
            return {k: v for k, v in self.storage[collection].items() if k.startswith(prefix)}
        return self.storage[collection]
    
    async def values(self, collection):
        if collection not in self.storage:
            return []
        return list(self.storage[collection].values())


@pytest.fixture
def temp_dir():
    """创建临时目录用于测试"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def voidrail_client():
    """创建文档转换客户端"""
    return SimpleVoidrailClient()


@pytest.fixture
def doc_service(temp_dir, voidrail_client):
    """创建文档服务实例"""
    service = DocumentService(
        base_dir=temp_dir,
        max_file_size=5 * 1024 * 1024,  # 5MB限制
        max_total_size_per_user=20 * 1024 * 1024,  # 20MB总限制
        voidrail_client=voidrail_client,
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
    print(f"创建结果: {result.success}, 数据: {result.data}")
    
    # 验证结果
    assert result.success
    assert result.data["document_id"] == doc_info["document_id"]
    
    # 获取文档并打印详细信息
    doc = await doc_service.get_document(user_id, doc_info["document_id"])
    print(f"获取到的文档: {doc}")
    
    # 验证能够获取创建的文档
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
    """测试转换文档为Markdown"""
    # 上传文件
    file = await upload_file()
    upload_result = await doc_service.upload_document(user_id, file)
    document_id = upload_result.data["document_id"]
    
    # 获取上传后的文档状态
    doc_before = await doc_service.get_document(user_id, document_id)
    print(f"上传后文档状态: {doc_before}")
    
    # 转换为Markdown
    convert_result = await doc_service.convert_to_markdown(user_id, document_id)
    print(f"转换结果: {convert_result.success}, 状态: {convert_result.data.get('state') if convert_result.success else 'N/A'}")
    
    # 验证结果
    assert convert_result.success
    assert convert_result.data["document_id"] == document_id
    assert convert_result.data["state"] == "markdowned"
    assert convert_result.data["sub_state"] == "completed"
    
    # 验证Markdown文件是否创建
    md_path = doc_service.processor.get_md_path(user_id, document_id)
    assert md_path.exists()
    
    # 验证元数据状态是否更新
    doc = await doc_service.get_document(user_id, document_id)
    assert doc["state"] == "markdowned"
    assert doc["has_markdown"] is True


@pytest.mark.asyncio
async def test_chunk_document(doc_service, user_id, upload_file):
    """测试文档分块"""
    # 上传文件并转换为Markdown
    file = await upload_file()
    upload_result = await doc_service.upload_document(user_id, file)
    document_id = upload_result.data["document_id"]
    await doc_service.convert_to_markdown(user_id, document_id)
    
    # 执行文档分块
    chunk_result = await doc_service.chunk_document(user_id, document_id)
    
    # 验证结果
    assert chunk_result["document_id"] == document_id
    assert chunk_result["state"] == "chunked"
    assert chunk_result["sub_state"] == "completed"
    assert "chunks_count" in chunk_result
    assert chunk_result["chunks_count"] > 0
    
    # 验证分块文件是否创建
    chunks_dir = doc_service.processor.get_chunks_dir(user_id, document_id)
    assert chunks_dir.exists()
    assert len(list(chunks_dir.glob("chunk_*.txt"))) == chunk_result["chunks_count"]
    
    # 验证元数据状态是否更新
    doc = await doc_service.get_document(user_id, document_id)
    assert doc["state"] == "chunked"
    assert doc["has_chunks"] is True


@pytest.mark.asyncio
async def test_generate_embeddings(doc_service, user_id, upload_file):
    """测试生成文档嵌入向量"""
    # 上传文件并处理
    file = await upload_file()
    upload_result = await doc_service.upload_document(user_id, file)
    document_id = upload_result.data["document_id"]
    await doc_service.convert_to_markdown(user_id, document_id)
    await doc_service.chunk_document(user_id, document_id)
    
    # 生成嵌入向量
    embed_result = await doc_service.generate_embeddings(user_id, document_id)
    
    # 验证结果
    assert embed_result["document_id"] == document_id
    assert embed_result["state"] == "embedded"
    assert embed_result["sub_state"] == "completed"
    assert "vectors_count" in embed_result
    assert embed_result["vectors_count"] > 0
    
    # 验证元数据状态是否更新
    doc = await doc_service.get_document(user_id, document_id)
    assert doc["state"] == "embedded"
    assert doc["has_embeddings"] is True


@pytest.mark.asyncio
async def test_rollback_to_previous_state(doc_service, user_id, upload_file):
    """测试回滚到上一个状态"""
    # 上传文件并转换为Markdown
    file = await upload_file()
    upload_result = await doc_service.upload_document(user_id, file)
    document_id = upload_result.data["document_id"]
    await doc_service.convert_to_markdown(user_id, document_id)
    
    # 回滚到上一个状态
    rollback_result = await doc_service.rollback_to_previous_state(user_id, document_id)
    
    # 验证结果
    assert rollback_result["document_id"] == document_id
    assert rollback_result["state"] == "uploaded"
    assert rollback_result["has_markdown"] is False
    
    # 验证Markdown文件是否已删除
    md_path = doc_service.processor.get_md_path(user_id, document_id)
    assert not md_path.exists()


@pytest.mark.asyncio
async def test_delete_document(doc_service, user_id, upload_file):
    """测试删除文档"""
    # 上传文件并转换为Markdown
    file = await upload_file()
    upload_result = await doc_service.upload_document(user_id, file)
    document_id = upload_result.data["document_id"]
    await doc_service.convert_to_markdown(user_id, document_id)
    
    # 删除文档
    delete_result = await doc_service.delete_document(user_id, document_id)
    
    # 验证结果
    assert delete_result.success
    assert delete_result.data["deleted"] is True
    assert delete_result.data["document_id"] == document_id
    
    # 验证文件是否已删除
    raw_path = doc_service.processor.get_raw_path(user_id, document_id)
    md_path = doc_service.processor.get_md_path(user_id, document_id)
    chunks_dir_path = doc_service.processor.get_chunks_dir_path(user_id, document_id)
    
    assert not raw_path.exists()
    assert not md_path.exists()
    assert not chunks_dir_path.exists()
    
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
async def test_sequential_document_processing(doc_service, user_id, upload_file):
    """测试完整的文档处理流程"""
    # 上传文件
    file = await upload_file()
    upload_result = await doc_service.upload_document(user_id, file)
    document_id = upload_result.data["document_id"]
    
    # 转换为Markdown
    md_result = await doc_service.convert_to_markdown(user_id, document_id)
    assert md_result.success
    assert md_result.data["state"] == "markdowned"
    
    # 分块
    chunk_result = await doc_service.chunk_document(user_id, document_id)
    assert chunk_result["state"] == "chunked"
    
    # 生成嵌入向量
    embed_result = await doc_service.generate_embeddings(user_id, document_id)
    assert embed_result["state"] == "embedded"
    
    # 获取文档最终状态
    doc = await doc_service.get_document(user_id, document_id)
    assert doc["state"] == "embedded"
    assert doc["has_markdown"] is True
    assert doc["has_chunks"] is True
    assert doc["has_embeddings"] is True


@pytest.fixture(scope="function", autouse=True)
async def cleanup_async_tasks():
    yield
    # 等待所有挂起的任务完成
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)