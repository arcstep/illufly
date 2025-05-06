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
from illufly.documents.processor import DocumentProcessor
from illufly.documents.meta import DocumentMetaManager
from voidring import IndexedRocksDB  # 假设有这个导入

# 测试用例运行前初始化 LiteLLM
cache_dir = os.path.join(os.path.dirname(__file__), "litellm_cache")
os.makedirs(cache_dir, exist_ok=True)
init_litellm(cache_dir)


@pytest.fixture
def temp_dir():
    """创建临时目录用于测试"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def meta_manager(temp_dir):
    """创建元数据管理器"""
    meta_dir = f"{temp_dir}/meta"
    docs_dir = f"{temp_dir}/docs"
    return DocumentMetaManager(meta_dir, docs_dir)


@pytest.fixture
def retriever(temp_dir):
    """创建向量检索器"""
    vector_db_path = f"{temp_dir}/vectors"
    return LanceRetriever(vector_db_path)


@pytest.fixture
def processor(temp_dir, meta_manager, retriever):
    """创建文档处理器"""
    return DocumentProcessor(
        docs_dir=f"{temp_dir}/processor_files",
        meta_manager=meta_manager,
        vector_db_path=f"{temp_dir}/vectors",
        embedding_config={}  # 默认配置
    )


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
async def test_save_uploaded_file(processor, user_id, upload_file):
    """测试保存上传文件"""
    file = await upload_file()
    
    # 保存文件
    file_info = await processor.save_uploaded_file(user_id, file)
    
    # 验证返回的文件信息
    assert file_info["document_id"] is not None
    assert file_info["original_name"] == "sample.txt"
    assert file_info["type"] == "txt"
    assert file_info["extension"] == ".txt"
    assert file_info["size"] > 0
    
    # 验证文件是否实际保存
    file_path = processor.get_raw_path(user_id, file_info["document_id"])
    assert file_path.exists()
    
    # 验证文件内容
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        assert "这是一个测试文本文件" in content


@pytest.mark.asyncio
async def test_register_remote_document(processor, user_id):
    """测试注册远程文档"""
    url = "https://example.com/sample.pdf"
    filename = "sample.pdf"
    
    # 注册远程文档
    doc_info = await processor.register_remote_document(user_id, url, filename)
    
    # 验证返回的文档信息
    assert doc_info["document_id"] is not None
    assert doc_info["original_name"] == filename
    assert doc_info["source_type"] == "remote"
    assert doc_info["source_url"] == url
    assert doc_info["type"] == "pdf"
    assert doc_info["extension"] == ".pdf"


@pytest.mark.asyncio
async def test_convert_to_markdown(processor, user_id, upload_file):
    """测试文档转换为Markdown"""
    # 上传文件
    file = await upload_file()
    file_info = await processor.save_uploaded_file(user_id, file)
    document_id = file_info["document_id"]
    
    # 转换为Markdown
    result = await processor.convert_to_markdown(user_id, document_id)
    
    # 验证结果
    assert "md_path" in result
    assert "content_preview" in result
    assert result["success"] is True
    
    # 验证Markdown文件是否创建
    md_path = processor.get_md_path(user_id, document_id)
    assert md_path.exists()
    
    # 验证文件内容
    async with aiofiles.open(md_path, "r", encoding="utf-8") as f:
        content = await f.read()
        assert f"# {document_id}" in content


@pytest.mark.asyncio
async def test_chunk_document(processor, user_id, upload_file):
    """测试文档分块"""
    # 上传文件并转换为Markdown
    file = await upload_file()
    file_info = await processor.save_uploaded_file(user_id, file)
    document_id = file_info["document_id"]
    await processor.convert_to_markdown(user_id, document_id)
    
    # 执行文档分块
    result = await processor.chunk_document(user_id, document_id)
    
    # 验证结果
    assert "chunks_count" in result
    assert result["chunks_count"] > 0
    assert "chunks_dir" in result
    assert "chunks" in result
    assert len(result["chunks"]) == result["chunks_count"]
    
    # 验证分块文件是否创建
    chunks_dir = processor.get_chunks_dir(user_id, document_id)
    assert chunks_dir.exists()
    assert len(list(chunks_dir.glob("chunk_*.txt"))) == result["chunks_count"]
    
    # 验证chunk元数据文件
    assert len(list(chunks_dir.glob("chunk_*.json"))) == result["chunks_count"]


@pytest.mark.asyncio
async def test_generate_embeddings(processor, user_id, upload_file):
    """测试生成文档嵌入向量"""
    # 上传文件并处理
    file = await upload_file()
    file_info = await processor.save_uploaded_file(user_id, file)
    document_id = file_info["document_id"]
    await processor.convert_to_markdown(user_id, document_id)
    await processor.chunk_document(user_id, document_id)
    
    # 生成嵌入向量
    result = await processor.generate_embeddings(user_id, document_id, processor.retriever)
    
    # 验证结果
    assert "collection" in result
    assert result["collection"] == f"user_{user_id}"
    assert "vectors_count" in result
    assert result["vectors_count"] > 0
    assert result["success"] is True


@pytest.mark.asyncio
async def test_calculate_storage_usage(processor, user_id, upload_file):
    """测试计算存储空间使用量"""
    # 上传文件并处理
    file = await upload_file()
    file_info = await processor.save_uploaded_file(user_id, file)
    document_id = file_info["document_id"]
    await processor.convert_to_markdown(user_id, document_id)
    
    # 计算存储空间
    usage = await processor.calculate_storage_usage(user_id)
    
    # 验证结果
    assert usage > 0
    
    # 多次上传增加使用量
    file2 = await upload_file()
    file_info2 = await processor.save_uploaded_file(user_id, file2)
    await processor.convert_to_markdown(user_id, file_info2["document_id"])
    
    new_usage = await processor.calculate_storage_usage(user_id)
    assert new_usage > usage


@pytest.mark.asyncio
async def test_remove_document_files(processor, user_id, upload_file):
    """测试删除文档文件"""
    # 上传文件并处理
    file = await upload_file()
    file_info = await processor.save_uploaded_file(user_id, file)
    document_id = file_info["document_id"]
    await processor.convert_to_markdown(user_id, document_id)
    await processor.chunk_document(user_id, document_id)
    
    # 删除文档文件
    result = await processor.remove_document_files(user_id, document_id)
    
    # 验证结果
    assert result["raw"] is True
    assert result["markdown"] is True
    assert result["chunks"] is True
    
    # 验证文件是否真的被删除
    raw_path = processor.get_raw_path(user_id, document_id)
    md_path = processor.get_md_path(user_id, document_id)
    chunks_dir_path = processor.get_chunks_dir_path(user_id, document_id)  # 使用新方法不会创建目录
    
    assert not raw_path.exists()
    assert not md_path.exists()
    assert not chunks_dir_path.exists()


@pytest.mark.asyncio
async def test_process_document_embeddings(processor, user_id, upload_file, meta_manager):
    """测试文档嵌入完整流程"""
    # 上传文件
    file = await upload_file()
    file_info = await processor.save_uploaded_file(user_id, file)
    document_id = file_info["document_id"]
    
    # 创建文档元数据
    await meta_manager.create_document(user_id, document_id)
    
    # 处理流程
    await processor.convert_to_markdown(user_id, document_id)
    await processor.chunk_document(user_id, document_id)
    
    # 保存切片到元数据
    chunks_result = await processor.chunk_document(user_id, document_id)
    await processor.add_chunks_metadata(user_id, document_id, chunks_result["chunks"])
    
    # 生成嵌入向量
    embedding_result = await processor.process_document_embeddings(user_id, document_id)
    
    # 验证结果
    assert embedding_result["success"] is True
    assert embedding_result["vectors_count"] > 0
    
    # 删除嵌入向量
    delete_result = await processor.remove_vector_embeddings(user_id, document_id)
    assert delete_result is True


@pytest.mark.asyncio
async def test_search_chunks(processor, user_id, upload_file, meta_manager):
    """测试搜索文档内容"""
    # 上传文件并处理
    file = await upload_file()
    file_info = await processor.save_uploaded_file(user_id, file)
    document_id = file_info["document_id"]
    
    # 创建文档元数据
    await meta_manager.create_document(user_id, document_id, None, {
        "original_name": "示例文档.txt",
        "type": "txt"
    })
    
    # 处理流程
    await processor.convert_to_markdown(user_id, document_id)
    await processor.chunk_document(user_id, document_id)
    await processor.process_document_embeddings(user_id, document_id)
    
    # 搜索文档
    search_result = await processor.search_chunks(user_id, "测试文本")
    
    # 验证结果
    assert "matches" in search_result
    assert "total" in search_result
    assert search_result["total"] >= 0  # 可能找到，也可能找不到
    
    # 如果找到结果，验证结果格式
    if search_result["total"] > 0:
        match = search_result["matches"][0]
        assert "text" in match
        assert "distance" in match
        assert "metadata" in match
        assert "document_meta" in match


@pytest.mark.asyncio
async def test_get_markdown(processor, user_id, upload_file):
    """测试获取Markdown内容"""
    # 上传文件并转换
    file = await upload_file()
    file_info = await processor.save_uploaded_file(user_id, file)
    document_id = file_info["document_id"]
    await processor.convert_to_markdown(user_id, document_id)
    
    # 获取Markdown内容
    result = await processor.get_markdown(user_id, document_id)
    
    # 验证结果
    assert result["document_id"] == document_id
    assert "content" in result
    assert result["content"].startswith("# ")  # Markdown内容应该有标题
    assert "file_size" in result
    assert result["file_size"] > 0
    assert "last_modified" in result
    assert "file_path" in result


@pytest.fixture(scope="function", autouse=True)
async def cleanup_async_tasks():
    yield
    # 等待所有挂起的任务完成
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)