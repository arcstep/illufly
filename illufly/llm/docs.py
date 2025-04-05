from typing import List, Dict, Any, Optional, Union, Tuple
import uuid
import time
import json
import logging
import asyncio
from pathlib import Path
import aiohttp
import aiofiles

# 简化docling导入方式
try:
    from docling import DocumentConverter, WebLoader
    DOCLING_AVAILABLE = True
except ImportError:
    DOCLING_AVAILABLE = False

from pydantic import BaseModel, Field

from ..rocksdb import IndexedRocksDB
from ..upload.base import UploadService, FileStatus
from .retriever import ChromaRetriever
from .chunking import DocumentChunker, ChunkingStrategy

logger = logging.getLogger(__name__)

class DocumentSource:
    """文档来源类型"""
    UPLOAD = "upload"  # 用户上传
    WEB = "web"        # 网页抓取
    API = "api"        # API调用

class DocumentChunk(BaseModel):
    """文档切片模型"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    doc_id: str
    user_id: str
    content: str
    sequence: int
    meta: Dict[str, Any] = {}
    created_at: float = Field(default_factory=time.time)
    
    @classmethod
    def get_prefix(cls, user_id: str, doc_id: str) -> str:
        return f"doc:chunk:{user_id}:{doc_id}:"
    
    @classmethod
    def get_key(cls, user_id: str, doc_id: str, chunk_id: str) -> str:
        return f"{cls.get_prefix(user_id, doc_id)}:{chunk_id}"
    
    @classmethod
    def register_indexes(cls, db: IndexedRocksDB):
        db.register_model(cls.__name__, cls)
        db.register_index(cls.__name__, cls, "created_at")

class Document(BaseModel):
    """文档模型"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    title: str
    description: str = ""
    type: str
    file_path: str
    source_type: str = DocumentSource.UPLOAD
    source: str = ""  # 源URL或文件名
    chunks_count: int = 0
    created_at: float = Field(default_factory=time.time)
    
    @classmethod
    def get_prefix(cls, user_id: str) -> str:
        return f"doc:{user_id}:"

    @classmethod
    def get_key(cls, user_id: str, doc_id: str) -> str:
        return f"{cls.get_prefix(user_id)}:{doc_id}"
        
    @classmethod
    def register_indexes(cls, db: IndexedRocksDB):
        db.register_model(cls.__name__, cls)
        db.register_index(cls.__name__, cls, "created_at")

class DocumentManager:
    """文档管理器
    
    负责处理文档的切片、存储和检索
    """
    
    def __init__(
        self, 
        db: IndexedRocksDB, 
        file_service: UploadService = None,
        collection_name: str = "documents",
        chunking_strategy: ChunkingStrategy = ChunkingStrategy.SIMPLE,
        chunk_size: int = 500,
        chunk_overlap: int = 50
    ):
        """初始化文档管理器
        
        Args:
            db: RocksDB实例
            file_service: 文件存储服务
            collection_name: 向量存储集合名
            chunking_strategy: 文档切片策略
            chunk_size: 每个切片的大小（字符数）
            chunk_overlap: 相邻切片的重叠大小（字符数）
        """
        self.db = db
        self.collection_name = collection_name
        self.file_service = file_service
        
        # 初始化文档切片器
        self.chunker = DocumentChunker(
            strategy=chunking_strategy,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        
        # 注册模型索引
        Document.register_indexes(self.db)
        DocumentChunk.register_indexes(self.db)
        
        # 初始化向量检索器
        self.retriever = None
    
    async def init_retriever(self):
        """初始化检索器"""
        if self.retriever is None:
            self.retriever = ChromaRetriever()
            logger.info("文档检索器初始化完成")
    
    async def process_upload(
        self, 
        user_id: str, 
        file_info: Dict[str, Any], 
        title: str = None, 
        description: str = ""
    ) -> Document:
        """处理上传的文件
        
        Args:
            user_id: 用户ID
            file_info: 文件信息
            title: 文档标题（可选，默认使用文件名）
            description: 文档描述
            
        Returns:
            处理后的文档对象
        """
        # 使用文件名作为标题（如果未提供）
        if not title:
            title = file_info.get("original_name", "").split(".")[0]
        
        # 创建文档记录
        doc = Document(
            id=file_info["id"],
            user_id=user_id,
            title=title,
            description=description,
            type=file_info["type"],
            file_path=file_info["path"],
            source_type=DocumentSource.UPLOAD,
            source=file_info.get("original_name", "")
        )
        
        # 保存文档记录
        self.db.update_with_indexes(
            model_name=Document.__name__,
            key=Document.get_key(user_id, doc.id),
            value=doc
        )
        
        # 处理文档内容
        await self.process_document(user_id, doc.id)
        
        # 标记文件为保留状态（不会自动过期）
        if self.file_service:
            await self.file_service.preserve_file(user_id, doc.id)
        
        return doc
    
    async def process_web_url(
        self, 
        user_id: str, 
        url: str, 
        title: str = None, 
        description: str = ""
    ) -> Document:
        """处理网页链接
        
        使用docling的WebLoader和DocumentConverter处理网页内容
        
        Args:
            user_id: 用户ID
            url: 网页链接
            title: 文档标题（可选，默认使用网页标题）
            description: 文档描述
            
        Returns:
            处理后的文档对象
        """
        # 确保检索器已初始化
        await self.init_retriever()
        
        # 加载网页内容
        try:
            logger.info(f"开始加载网页: {url}")
            
            web_content = ""
            page_title = ""
            
            # 使用docling处理网页
            if DOCLING_AVAILABLE:
                try:
                    # 直接使用docling的WebLoader和DocumentConverter
                    loader = WebLoader()
                    web_doc = loader.load(url)
                    
                    converter = DocumentConverter()
                    result = converter.convert(source=web_doc)
                    
                    # 提取内容和标题
                    if hasattr(result, 'document'):
                        # 保留文档结构使用Markdown
                        if hasattr(result.document, 'export_to_markdown'):
                            web_content = result.document.export_to_markdown()
                        elif hasattr(result.document, 'export_to_text'):
                            web_content = result.document.export_to_text()
                    
                    # 获取标题
                    if hasattr(web_doc, 'title'):
                        page_title = web_doc.title
                    
                    logger.info(f"使用docling成功处理网页: {url}")
                except Exception as e:
                    logger.warning(f"docling处理网页失败，回退到HTTP请求: {str(e)}")
                    web_content = ""
            
            # 如果docling处理失败，使用HTTP请求
            if not web_content:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            raise ValueError(f"网页请求失败，状态码: {response.status}")
                        
                        web_content = await response.text()
                        
                        # 提取标题
                        if not page_title and "<title>" in web_content.lower():
                            start_idx = web_content.lower().find("<title>") + 7
                            end_idx = web_content.lower().find("</title>")
                            if start_idx < end_idx:
                                page_title = web_content[start_idx:end_idx].strip()
            
            # 使用提取的标题
            if not title and page_title:
                title = page_title
            elif not title:
                title = url.split("/")[-1]
            
            logger.info(f"网页加载成功: {url}, 内容长度: {len(web_content)}")
            
            # 确定文件类型并保存内容
            file_type = "html"
            file_info = None
            
            if self.file_service:
                file_info = await self.file_service.save_web_file(
                    user_id=user_id,
                    url=url,
                    file_content=web_content.encode('utf-8'),
                    file_type=file_type,
                    status=FileStatus.PRESERVED
                )
            else:
                file_id = str(uuid.uuid4())
                file_info = {
                    "id": file_id,
                    "type": file_type,
                    "path": "",
                    "original_name": url.split("/")[-1]
                }
            
            # 创建文档记录
            doc = Document(
                id=file_info["id"],
                user_id=user_id,
                title=title,
                description=description,
                type=file_type,
                file_path=file_info["path"],
                source_type=DocumentSource.WEB,
                source=url
            )
            
            # 保存文档记录
            self.db.update_with_indexes(
                model_name=Document.__name__,
                key=Document.get_key(user_id, doc.id),
                value=doc
            )
            
            # 文档切片
            chunks = self._chunk_document(web_content)
            doc.chunks_count = len(chunks)
            
            # 保存切片并向量化
            await self._save_chunks(user_id, doc.id, chunks)
            
            # 更新文档记录
            self.db.update_with_indexes(
                model_name=Document.__name__,
                key=Document.get_key(user_id, doc.id),
                value=doc
            )
            
            return doc
        except Exception as e:
            logger.error(f"处理网页链接失败: {url}, 错误: {str(e)}")
            raise ValueError(f"无法加载网页内容: {str(e)}")
    
    async def process_document(self, user_id: str, doc_id: str) -> Document:
        """处理文档，包括解析、切片、存储和向量化
        
        Args:
            user_id: 用户ID
            doc_id: 文档ID
            
        Returns:
            处理后的文档对象
        """
        # 确保检索器已初始化
        await self.init_retriever()
        
        # 获取文档
        doc = await self.get_document(user_id, doc_id)
        if not doc:
            raise ValueError(f"文档不存在: {doc_id}")
        
        # 解析文档
        doc_content = await self._parse_document(doc.file_path, doc.type)
        
        # 切片文档并存储
        chunks = self._chunk_document(doc_content)
        doc.chunks_count = len(chunks)
        
        # 保存切片并向量化
        await self._save_chunks(user_id, doc_id, chunks)
        
        # 更新文档记录（更新chunks_count）
        self.db.update_with_indexes(
            model_name=Document.__name__,
            key=Document.get_key(user_id, doc_id),
            value=doc
        )
        
        return doc
    
    async def _parse_document(self, file_path: str, file_type: str) -> str:
        """解析文档内容
        
        直接使用docling的DocumentConverter处理文档
        
        Args:
            file_path: 文件路径
            file_type: 文件类型
            
        Returns:
            文档内容
        """
        path = Path(file_path)
        
        # 处理简单文本和HTML文件
        if file_type == 'txt':
            async with aiofiles.open(path, 'r', encoding='utf-8') as f:
                return await f.read()
        
        elif file_type == 'html':
            async with aiofiles.open(path, 'r', encoding='utf-8') as f:
                html_content = await f.read()
                return html_content
        
        # 对于其他格式，使用docling进行处理
        elif DOCLING_AVAILABLE:
            try:
                # 使用docling处理文档 - 简单直接
                converter = DocumentConverter()
                result = converter.convert(source=str(path))
                
                # 优先使用Markdown导出，保留更多结构信息
                if hasattr(result, 'document'):
                    if hasattr(result.document, 'export_to_markdown'):
                        return result.document.export_to_markdown()
                    elif hasattr(result.document, 'export_to_text'):
                        return result.document.export_to_text()
                
                logger.warning(f"docling无法解析文档内容: {file_path}")
                return f"无法从文档中提取文本内容"
            except Exception as e:
                logger.error(f"docling处理文档失败: {file_path}, 错误: {str(e)}")
        
        # 如果docling不可用或处理失败，尝试读取原始文件
        try:
            if file_type in ['txt', 'html', 'md', 'markdown']:
                async with aiofiles.open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    return await f.read()
            else:
                return f"不支持的文件类型或无法处理: {file_type}"
        except Exception as e:
            logger.error(f"读取文件失败: {file_path}, 错误: {str(e)}")
            return f"无法读取文件: {str(e)}"
    
    def _chunk_document(self, content: str) -> List[str]:
        """切片文档内容
        
        Args:
            content: 文档内容
            
        Returns:
            切片列表
        """
        return self.chunker.chunk_text(content)
    
    async def _save_chunks(self, user_id: str, doc_id: str, chunks: List[str]):
        """保存切片并向量化
        
        Args:
            user_id: 用户ID
            doc_id: 文档ID
            chunks: 切片列表
        """
        all_texts = []
        all_metadatas = []
        all_ids = []
        
        for i, chunk_text in enumerate(chunks):
            # 创建切片对象
            chunk = DocumentChunk(
                doc_id=doc_id,
                user_id=user_id,
                content=chunk_text,
                sequence=i,
                meta={
                    "doc_id": doc_id,
                    "sequence": i
                }
            )
            
            # 保存切片
            self.db.update_with_indexes(
                model_name=DocumentChunk.__name__,
                key=DocumentChunk.get_key(user_id, doc_id, chunk.id),
                value=chunk
            )
            
            # 准备向量化数据
            all_texts.append(chunk_text)
            all_metadatas.append({
                "doc_id": doc_id,
                "chunk_id": chunk.id,
                "user_id": user_id,
                "sequence": i
            })
            all_ids.append(chunk.id)
        
        # 向量化存储
        await self.retriever.add(
            texts=all_texts,
            collection_name=self.collection_name,
            metadatas=all_metadatas,
            ids=all_ids,
            user_id=user_id
        )
    
    async def get_document(self, user_id: str, doc_id: str) -> Optional[Document]:
        """获取文档
        
        Args:
            user_id: 用户ID
            doc_id: 文档ID
            
        Returns:
            文档对象，如果不存在则返回None
        """
        key = Document.get_key(user_id, doc_id)
        return self.db.get(key)
    
    async def get_documents(self, user_id: str) -> List[Document]:
        """获取用户所有文档
        
        Args:
            user_id: 用户ID
            
        Returns:
            文档列表
        """
        prefix = Document.get_prefix(user_id)
        return self.db.values(prefix=prefix)
    
    async def delete_document(self, user_id: str, doc_id: str) -> bool:
        """删除文档及其切片
        
        Args:
            user_id: 用户ID
            doc_id: 文档ID
            
        Returns:
            是否删除成功
        """
        # 确保检索器已初始化
        await self.init_retriever()
        
        # 获取文档
        doc = await self.get_document(user_id, doc_id)
        if not doc:
            return False
        
        # 获取所有切片ID
        prefix = DocumentChunk.get_prefix(user_id, doc_id)
        chunks = self.db.values(prefix=prefix)
        chunk_ids = [chunk.id for chunk in chunks]
        
        # 从向量存储中删除
        if chunk_ids:
            await self.retriever.delete(
                collection_name=self.collection_name,
                ids=chunk_ids,
                user_id=user_id
            )
        
        # 删除所有切片
        for chunk in chunks:
            key = DocumentChunk.get_key(user_id, doc_id, chunk.id)
            self.db.delete(key)
        
        # 删除文档
        key = Document.get_key(user_id, doc_id)
        self.db.delete(key)
        
        # 删除文件（如果有文件服务）
        if self.file_service and doc.file_path:
            await self.file_service.delete_file(user_id, doc_id)
        
        return True
    
    async def get_chunks(self, user_id: str, doc_id: str) -> List[DocumentChunk]:
        """获取文档的所有切片
        
        Args:
            user_id: 用户ID
            doc_id: 文档ID
            
        Returns:
            切片列表
        """
        prefix = DocumentChunk.get_prefix(user_id, doc_id)
        chunks = self.db.values(prefix=prefix)
        
        # 按序号排序
        return sorted(chunks, key=lambda x: x.sequence)
    
    async def search_chunks(self, user_id: str, doc_id: str, query: str, top_k: int = 5) -> List[DocumentChunk]:
        """搜索文档内的切片
        
        Args:
            user_id: 用户ID
            doc_id: 文档ID
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            匹配的切片列表
        """
        # 确保检索器已初始化
        await self.init_retriever()
        
        # 构建过滤条件
        filter_condition = {
            "user_id": user_id,
            "doc_id": doc_id
        }
        
        # 执行查询
        results = await self.retriever.query(
            query_texts=[query],
            collection_name=self.collection_name,
            filter_condition=filter_condition,
            top_k=top_k
        )
        
        # 如果没有结果，返回空列表
        if not results or not results["ids"] or not results["ids"][0]:
            return []
        
        # 获取匹配的切片ID
        chunk_ids = results["ids"][0]
        
        # 加载切片对象
        chunks = []
        for chunk_id in chunk_ids:
            key = DocumentChunk.get_key(user_id, doc_id, chunk_id)
            chunk = self.db.get(key)
            if chunk:
                chunks.append(chunk)
        
        return chunks
    
    async def search_documents(self, user_id: str, query: str, top_k: int = 3) -> List[Tuple[Document, List[DocumentChunk]]]:
        """全局搜索文档
        
        Args:
            user_id: 用户ID
            query: 查询文本
            top_k: 每个文档的返回结果数量
            
        Returns:
            匹配的文档和切片列表
        """
        # 确保检索器已初始化
        await self.init_retriever()
        
        # 构建过滤条件
        filter_condition = {
            "user_id": user_id
        }
        
        # 执行查询
        results = await self.retriever.query(
            query_texts=[query],
            collection_name=self.collection_name,
            filter_condition=filter_condition,
            top_k=20  # 获取较多结果供过滤
        )
        
        # 如果没有结果，返回空列表
        if not results or not results["ids"] or not results["ids"][0]:
            return []
        
        # 获取匹配的切片ID和元数据
        chunk_ids = results["ids"][0]
        metadatas = results["metadatas"][0]
        
        # 按文档分组结果
        doc_chunks = {}
        for chunk_id, metadata in zip(chunk_ids, metadatas):
            doc_id = metadata.get("doc_id")
            if not doc_id:
                continue
                
            if doc_id not in doc_chunks:
                doc_chunks[doc_id] = []
                
            key = DocumentChunk.get_key(user_id, doc_id, chunk_id)
            chunk = self.db.get(key)
            if chunk:
                doc_chunks[doc_id].append(chunk)
        
        # 获取文档信息并按相关性排序
        search_results = []
        for doc_id, chunks in doc_chunks.items():
            doc = await self.get_document(user_id, doc_id)
            if doc:
                # 最多返回top_k个切片
                search_results.append((doc, chunks[:top_k]))
        
        return search_results
