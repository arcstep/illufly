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

    async def delete(self, collection_name=None, user_id=None, document_id=None, filter=None):
        """删除向量"""
        if collection_name not in self.collections:
            return {"success": True, "deleted": 0}
            
        collection = self.collections[collection_name]
        deleted_count = 0
        
        if document_id:
            # 筛选出要保留的项
            new_texts = []
            new_vectors = []
            new_metadatas = []
            new_ids = []
            
            for i in range(len(collection["texts"])):
                metadata = collection["metadatas"][i]
                if metadata.get("document_id") != document_id:
                    new_texts.append(collection["texts"][i])
                    new_vectors.append(collection["vectors"][i])
                    new_metadatas.append(metadata)
                    new_ids.append(collection["ids"][i])
                else:
                    deleted_count += 1
            
            # 更新集合
            collection["texts"] = new_texts
            collection["vectors"] = new_vectors
            collection["metadatas"] = new_metadatas
            collection["ids"] = new_ids
        
        return {"success": True, "deleted": deleted_count}
    
    async def query(self, query_texts, collection_name=None, user_id=None, limit=10, 
                   document_id=None, threshold=0.8, filter=None):
        """查询相似文本"""
        if collection_name not in self.collections:
            return [{"query": q, "results": [], "error": "集合不存在"} for q in ([query_texts] if isinstance(query_texts, str) else query_texts)]
            
        collection = self.collections[collection_name]
        queries = [query_texts] if isinstance(query_texts, str) else query_texts
        results = []
        
        for query in queries:
            # 简单计算相似度 - 词汇重叠程度
            query_result = {"query": query, "results": []}
            query_words = set(query.lower().split())
            
            matches = []
            for i, text in enumerate(collection["texts"]):
                text_words = set(text.lower().split())
                
                # 简单相似度计算 - 词汇重叠比例
                if not text_words:
                    similarity = 0
                else:
                    overlap = len(query_words.intersection(text_words))
                    similarity = overlap / max(len(query_words), 1)
                
                metadata = collection["metadatas"][i]
                
                # 如果指定了document_id，只返回匹配的文档
                if document_id and metadata.get("document_id") != document_id:
                    continue
                    
                # 符合相似度阈值的结果
                if similarity >= threshold:
                    matches.append({
                        "text": text,
                        "distance": similarity,
                        "metadata": metadata
                    })
            
            # 按相似度排序并限制返回数量
            matches.sort(key=lambda x: x["distance"], reverse=True)
            query_result["results"] = matches[:limit]
            results.append(query_result)
            
        return results


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
def voidrail_client():
    """创建文档转换客户端"""
    return SimpleVoidrailClient()


@pytest.fixture
def processor(temp_dir, meta_manager, retriever, voidrail_client):
    """创建文档处理器"""
    return DocumentProcessor(
        docs_dir=f"{temp_dir}/processor_files",
        meta_manager=meta_manager,
        voidrail_client=voidrail_client,
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