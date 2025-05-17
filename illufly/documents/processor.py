import os
import shutil
import uuid
import time
import aiofiles
import json
import logging
import base64
from pathlib import Path
from typing import Dict, Any, List, Optional, AsyncGenerator
from fastapi import UploadFile
from voidrail import CeleryClient

from ..llm import LanceRetriever

CONVERT_SERVICE_NAME = "docling"
CONVERT_METHOD_NAME = "convert"

class DocumentProcessor:
    """处理文档转换的专用类 - 专注于文档处理的具体实现"""
    
    def __init__(
        self, 
        docs_dir: str, 
        meta_manager,
        max_file_size: int = 50 * 1024 * 1024, 
        allowed_extensions: List[str] = None,
        vector_db_path: str = None,
        embedding_config: Dict[str, Any] = {},
        logger = None
    ):
        self.docs_dir = Path(docs_dir)
        self.meta_manager = meta_manager
        self.max_file_size = max_file_size
        self.allowed_extensions = allowed_extensions or [
            '.pptx', '.md', '.markdown', '.pdf', '.docx', '.txt',
            '.jpg', '.jpeg', '.png', '.gif', '.webp'
        ]
        self.voidrail_client = CeleryClient(CONVERT_SERVICE_NAME)
        self.logger = logger or logging.getLogger(__name__)
        
        # 初始化向量检索器
        if vector_db_path:
            self.retriever = LanceRetriever(
                output_dir=vector_db_path,
                embedding_config=embedding_config,
                metric="cosine"
            )
        else:
            self.retriever = None
        
        # 确保基础目录存在
        self.docs_dir.mkdir(parents=True, exist_ok=True)
    
    # ==== 基础操作方法 ====
    
    def get_path(self, *parts) -> Path:
        """仅获取路径，不创建目录"""
        return Path(self.docs_dir).joinpath(*parts)

    def get_user_path(self, user_id: str, subdir: str) -> Path:
        """仅获取用户子目录路径，不创建目录"""
        return self.get_path(user_id, subdir)
    
    def ensure_user_dir(self, user_id: str, subdir: str) -> Path:
        """确保用户子目录存在，并返回路径"""
        user_dir = self.get_user_path(user_id, subdir)
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    def get_user_dir(self, user_id: str, subdir: str) -> Path:
        """获取用户指定子目录（兼容旧代码）
        注意：此方法会创建目录，如果只需要路径请使用get_user_path"""
        return self.ensure_user_dir(user_id, subdir)

    def get_raw_path(self, user_id: str, document_id: str) -> Path:
        """获取原始文件路径"""
        return self.get_user_path(user_id, "raw") / document_id

    def ensure_raw_dir(self, user_id: str) -> Path:
        """确保原始文件目录存在"""
        return self.ensure_user_dir(user_id, "raw")

    def get_md_path(self, user_id: str, document_id: str) -> Path:
        """获取Markdown文件路径"""
        # 去除document_id中可能存在的后缀
        base_id = document_id.rsplit('.', 1)[0] if '.' in document_id else document_id
        return self.get_user_path(user_id, "md") / f"{base_id}.md"

    def ensure_md_dir(self, user_id: str) -> Path:
        """确保Markdown文件目录存在"""
        return self.ensure_user_dir(user_id, "md")
    
    def get_chunks_dir_path(self, user_id: str, document_id: str) -> Path:
        """获取切片目录路径，不创建目录"""
        return self.get_user_dir(user_id, "chunks") / document_id
    
    def ensure_chunks_dir_exists(self, user_id: str, document_id: str) -> Path:
        """确保切片目录存在，并返回路径"""
        chunks_dir = self.get_chunks_dir_path(user_id, document_id)
        chunks_dir.mkdir(exist_ok=True)
        return chunks_dir
    
    def get_chunks_dir(self, user_id: str, document_id: str) -> Path:
        """获取切片目录路径（兼容旧代码）
        注意：此方法会创建目录，如果只需要路径请使用get_chunks_dir_path"""
        return self.ensure_chunks_dir_exists(user_id, document_id)
    
    def generate_document_id(self, original_filename: str = None) -> str:
        """生成文档ID"""
        if original_filename:
            _, ext = os.path.splitext(original_filename)
            return f"{uuid.uuid4().hex}{ext.lower()}"
        return uuid.uuid4().hex
    
    def is_valid_file_type(self, file_name: str) -> bool:
        """检查文件类型是否有效"""
        _, ext = os.path.splitext(file_name)
        return ext.lower() in self.allowed_extensions
    
    def get_file_extension(self, file_name: str) -> str:
        """获取文件扩展名"""
        _, ext = os.path.splitext(file_name)
        return ext.lower()
    
    def get_file_type(self, file_name: str) -> str:
        """获取文件类型"""
        _, ext = os.path.splitext(file_name)
        return ext.lower()[1:]  # 去掉点号
    
    # ==== 简化的文件路径管理 ====
    
    def get_document_dir(self, user_id: str, document_id: str) -> Path:
        """获取文档目录路径"""
        doc_dir = self.get_path(user_id, document_id)
        doc_dir.mkdir(parents=True, exist_ok=True)
        return doc_dir
    
    def get_document_file_path(self, user_id: str, document_id: str, filename: str = None) -> Path:
        """获取文档文件路径，不指定文件名则返回原始文件路径"""
        doc_dir = self.get_document_dir(user_id, document_id)
        if filename:
            return doc_dir / filename
        # 默认使用document_id作为原始文件名
        base_name = document_id
        return doc_dir / base_name
    
    # ==== 文档处理核心方法 ====
    
    async def save_uploaded_file(self, user_id: str, file: UploadFile) -> Dict[str, Any]:
        """保存上传的文件并返回基本信息"""
        # 检查文件类型
        if not self.is_valid_file_type(file.filename):
            raise ValueError(f"不支持的文件类型: {file.filename}")
        
        # 生成文档ID和路径
        document_id = self.generate_document_id(file.filename)
        # 确保目录存在
        doc_dir = self.get_document_dir(user_id, document_id)
        file_path = self.get_document_file_path(user_id, document_id)
        
        # 保存文件
        file_size = 0
        async with aiofiles.open(file_path, 'wb') as out_file:
            while content := await file.read(1024 * 1024):  # 每次读取1MB
                file_size += len(content)
                if file_size > self.max_file_size:
                    await out_file.close()
                    os.remove(file_path)
                    raise ValueError(f"文件大小超过限制: {self.max_file_size} bytes")
                await out_file.write(content)
        
        # 返回基本信息
        return {
            "document_id": document_id,
            "original_name": file.filename,
            "size": file_size,
            "type": self.get_file_type(file.filename),
            "extension": self.get_file_extension(file.filename)
        }
    
    async def register_remote_document(self, user_id: str, url: str, filename: str) -> Dict[str, Any]:
        """注册远程文档"""
        # 检查文件类型
        if not self.is_valid_file_type(filename):
            raise ValueError(f"不支持的文件类型: {filename}")
        
        document_id = self.generate_document_id(filename)
        # 创建文档目录但不下载文件
        self.get_document_dir(user_id, document_id)
        
        # 返回基本信息
        return {
            "document_id": document_id,
            "original_name": filename,
            "source_type": "remote",
            "source_url": url,
            "type": self.get_file_type(filename),
            "extension": self.get_file_extension(filename)
        }
    
    async def convert_to_markdown(self, user_id: str, document_id: str) -> Dict[str, Any]:
        """将文档转换为Markdown格式
        
        支持直接处理本地文件或远程URL
        
        Args:
            user_id: 用户ID
            document_id: 文档ID
            
        Returns:
            转换结果信息字典
        """
        try:
            # 获取文档元数据
            doc_meta = await self.meta_manager.get_metadata(user_id, document_id)
            if not doc_meta:
                raise ValueError(f"找不到文档元数据: {document_id}")
            
            # 获取文件路径或URL
            doc_path = self.get_document_file_path(user_id, document_id)
            is_remote = doc_meta.get("source_type") == "remote"
            source_url = doc_meta.get("source_url") if is_remote else None
            file_type = doc_meta.get("type")
            
            # 处理纯文本文件类型 (本地)
            if not is_remote and file_type in ['md', 'markdown', 'txt']:
                self.logger.info(f"检测到纯文本文件: {document_id}，直接返回内容")
                async with aiofiles.open(doc_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = await f.read()
                return {
                    "content": content,
                    "content_preview": content[:200] + "..." if len(content) > 200 else content,
                    "success": True,
                    "method": "direct_read"
                }
            
            # 使用voidrail进行转换
            if not self.voidrail_client:
                raise ValueError("未配置转换服务，无法进行文档转换")
            
            # 准备转换参数
            conversion_params = {
                "file_type": file_type,
                "output_format": "markdown"
            }
            
            # 处理本地或远程文件
            if is_remote and source_url:
                # 直接使用URL进行转换
                self.logger.info(f"远程文档转换: {source_url}")
                conversion_params["content"] = source_url
                conversion_params["content_type"] = "url"
            else:
                # 本地文件转换
                if not doc_path.exists():
                    raise FileNotFoundError(f"找不到原始文档: {document_id}")
                    
                # 读取文件内容并转换为base64
                async with aiofiles.open(doc_path, 'rb') as f:
                    file_content = await f.read()
                    base64_content = base64.b64encode(file_content).decode('utf-8')
                    
                conversion_params["content"] = base64_content
                conversion_params["content_type"] = "base64"
            
            # 使用LLM服务转换
            markdown_content = ""
            async for chunk in self.voidrail_client.stream(
                f"{CONVERT_SERVICE_NAME}.{CONVERT_METHOD_NAME}",
                **conversion_params
            ):
                markdown_content += chunk
            
            return {
                "content": markdown_content,
                "content_preview": markdown_content[:200] + "..." if len(markdown_content) > 200 else markdown_content,
                "success": True,
                "method": "conversion"
            }
        except Exception as e:
            self.logger.error(f"转换Markdown失败: {e}")
            raise
    
    async def chunk_document(self, user_id: str, document_id: str) -> Dict[str, Any]:
        """将Markdown文档切分成段落"""
        md_path = self.get_md_path(user_id, document_id)
        chunks_dir = self.get_chunks_dir(user_id, document_id)
        
        # 检查Markdown文件是否存在
        if not md_path.exists():
            raise FileNotFoundError(f"找不到Markdown文件: {document_id}")
        
        try:
            # 读取Markdown内容
            async with aiofiles.open(md_path, 'r', encoding='utf-8') as f:
                content = await f.read()
            
            # 简单分段策略
            chunks = []
            current_chunk = ""
            for line in content.split('\n'):
                current_chunk += line + '\n'
                if len(current_chunk) > 1000 or (line.startswith('#') and current_chunk.strip() != line):
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
            
            # 添加最后一个块
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            
            # 保存各个分块到文件
            for i, chunk in enumerate(chunks):
                chunk_path = chunks_dir / f"chunk_{i}.txt"
                async with aiofiles.open(chunk_path, 'w', encoding='utf-8') as f:
                    await f.write(chunk)
                
                # 创建chunk元数据
                chunk_meta = {
                    "index": i,
                    "length": len(chunk),
                    "content": chunk,
                    "created_at": time.time()
                }
                
                # 可选：保存chunk元数据
                chunk_meta_path = chunks_dir / f"chunk_{i}.json"
                async with aiofiles.open(chunk_meta_path, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(chunk_meta, ensure_ascii=False))
            
            return {
                "chunks_count": len(chunks),
                "chunks_dir": str(chunks_dir),
                "chunks": chunks
            }
        except Exception as e:
            self.logger.error(f"切片文档失败: {e}")
            raise
    
    async def generate_embeddings(self, user_id: str, document_id: str, retriever=None) -> Dict[str, Any]:
        """生成文档切片的嵌入向量"""
        chunks_dir = self.get_chunks_dir(user_id, document_id)
        
        # 检查切片文件是否存在
        if not chunks_dir.exists() or not list(chunks_dir.glob("chunk_*.txt")):
            raise FileNotFoundError(f"找不到文档切片: {document_id}")
        
        if not retriever:
            raise ValueError("没有提供向量检索器")
        
        try:
            # 读取所有切片
            chunks = []
            chunk_paths = sorted(chunks_dir.glob("chunk_*.txt"), key=lambda p: int(p.stem.split('_')[1]))
            
            for i, chunk_path in enumerate(chunk_paths):
                async with aiofiles.open(chunk_path, 'r', encoding='utf-8') as f:
                    content = await f.read()
                
                chunks.append({
                    "text": content,
                    "metadata": {
                        "document_id": document_id,
                        "chunk_index": i,
                        "user_id": user_id
                    }
                })
            
            # 生成嵌入并保存到检索器
            collection_name = f"user_{user_id}"
            # 执行向量化
            await retriever.add(
                collection_name=collection_name,
                user_id=user_id,
                texts=[c["text"] for c in chunks],
                metadatas=[c["metadata"] for c in chunks],
                ids=[f"{document_id}_{i}" for i in range(len(chunks))]
            )
            
            return {
                "collection": collection_name,
                "vectors_count": len(chunks),
                "success": True
            }
        except Exception as e:
            self.logger.error(f"生成嵌入向量失败: {e}")
            raise
    
    # ==== 资源管理方法 ====
    
    async def calculate_storage_usage(self, user_id: str) -> int:
        """计算用户已使用的存储空间（字节）"""
        total_size = 0
        
        # 所有用户目录
        for subdir in ["raw", "md", "chunks"]:
            dir_path = self.get_user_dir(user_id, subdir)
            for item in dir_path.glob("**/*"):
                if item.is_file():
                    total_size += item.stat().st_size
        
        return total_size
    
    async def remove_document_files(self, user_id: str, document_id: str) -> Dict[str, bool]:
        """删除文档相关的所有文件"""
        results = {
            "raw": False,
            "markdown": False,
            "chunks": False
        }
        
        # 删除原始文件
        raw_path = self.get_raw_path(user_id, document_id)
        if raw_path.exists():
            try:
                os.remove(raw_path)
                results["raw"] = True
            except Exception as e:
                self.logger.error(f"删除原始文件失败: {e}")
        else:
            results["raw"] = True  # 文件不存在视为删除成功
            
        # 删除Markdown文件
        md_path = self.get_md_path(user_id, document_id)
        if md_path.exists():
            try:
                os.remove(md_path)
                results["markdown"] = True
            except Exception as e:
                self.logger.error(f"删除Markdown文件失败: {e}")
        else:
            results["markdown"] = True
            
        # 删除切片目录
        chunks_dir = self.get_chunks_dir(user_id, document_id)
        if chunks_dir.exists():
            try:
                shutil.rmtree(chunks_dir)
                results["chunks"] = True
            except Exception as e:
                self.logger.error(f"删除切片目录失败: {e}")
        else:
            results["chunks"] = True
            
        return results
    
    async def remove_markdown_file(self, user_id: str, document_id: str) -> bool:
        """删除Markdown文件"""
        md_path = self.get_md_path(user_id, document_id)
        if md_path.exists():
            try:
                os.remove(md_path)
                self.logger.info(f"已删除Markdown文件: {md_path}")
                return True
            except Exception as e:
                self.logger.error(f"删除Markdown文件失败: {e}")
        return False
    
    async def remove_chunks_dir(self, user_id: str, document_id: str) -> bool:
        """删除文档切片目录"""
        chunks_dir = self.get_chunks_dir(user_id, document_id)
        if chunks_dir.exists():
            try:
                # 直接删除目录
                shutil.rmtree(chunks_dir)
                self.logger.info(f"已删除切片目录: {chunks_dir}")
                return True
            except Exception as e:
                self.logger.error(f"删除切片目录失败: {e}")
        return False
    
    async def iter_chunks(self, user_id: str, document_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        """迭代文档的所有切片"""
        chunks_dir = self.get_chunks_dir(user_id, document_id)
        if not chunks_dir.exists():
            return
            
        chunk_paths = sorted(chunks_dir.glob("chunk_*.txt"), key=lambda p: int(p.stem.split('_')[1]))
        
        for i, chunk_path in enumerate(chunk_paths):
            try:
                async with aiofiles.open(chunk_path, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    
                # 可选：尝试读取元数据
                metadata = {}
                meta_path = chunks_dir / f"chunk_{i}.json"
                if meta_path.exists():
                    try:
                        async with aiofiles.open(meta_path, 'r', encoding='utf-8') as mf:
                            metadata = json.loads(await mf.read())
                    except:
                        pass
                        
                yield {
                    "document_id": document_id,
                    "chunk_index": i,
                    "content": content,
                    "metadata": metadata
                }
            except Exception as e:
                self.logger.error(f"读取切片失败: chunk_{i}.txt, 错误: {e}")
    
    # ==== 完整的文档处理流程 ====
    
    async def save_and_get_file_info(self, user_id: str, file: UploadFile, max_total_size: int = 200 * 1024 * 1024) -> Dict[str, Any]:
        """上传文档并返回文件信息，不创建元数据"""
        # 1. 检查存储空间
        current_usage = await self.calculate_storage_usage(user_id)
        if current_usage + file.size > max_total_size:
            raise ValueError(f"存储空间不足: 当前已使用 {current_usage} bytes")
        
        # 2. 保存上传文件
        file_info = await self.save_uploaded_file(user_id, file)
        
        # 3. 添加源类型信息
        file_info["source_type"] = "local"
        
        # 直接返回文件信息，不创建元数据
        return file_info
    
    async def register_remote_doc_info(self, user_id: str, url: str, filename: str) -> Dict[str, Any]:
        """注册远程文档并返回信息，不创建元数据"""
        # 1. 获取远程文档信息
        doc_info = await self.register_remote_document(user_id, url, filename)
        
        # 直接返回文档信息，不创建元数据
        return doc_info
    
    async def convert_document_to_markdown(self, user_id: str, document_id: str) -> Dict[str, Any]:
        """文件转换为Markdown - 只处理文件操作，不修改元数据"""
        try:
            result = await self.convert_to_markdown(user_id, document_id)
            return result
        except Exception as e:
            self.logger.error(f"转换Markdown失败: {e}")
            raise
    
    async def process_document_chunks(self, user_id: str, document_id: str) -> Dict[str, Any]:
        """文档分块 - 只处理文件操作，不修改元数据"""
        try:
            result = await self.chunk_document(user_id, document_id)
            return result
        except Exception as e:
            self.logger.error(f"文档切片失败: {e}")
            raise
    
    async def process_document_embeddings(self, user_id: str, document_id: str) -> Dict[str, Any]:
        """生成向量嵌入 - 使用主题路径的集合名称"""
        if not self.retriever:
            raise ValueError("没有配置向量检索器，无法生成嵌入")
        
        try:
            # 获取文档元数据
            doc_meta = await self.meta_manager.get_metadata(user_id, document_id)
            if not doc_meta:
                raise ValueError(f"找不到文档元数据: {document_id}")
            
            # 获取主题路径
            topic_path = doc_meta.get("topic_path", "")
            
            # 从主题路径提取集合名称
            collection_name = None
            if topic_path:
                extracted_collection = self.extract_collection_name_from_topic(user_id, topic_path)
                if extracted_collection:
                    collection_name = extracted_collection
                    # 保存集合名称到元数据
                    await self.meta_manager.update_metadata(
                        user_id, document_id, 
                        {"collection_name": collection_name}
                    )
            
            # 如果没有提取到集合名称，使用默认命名
            if not collection_name:
                collection_name = f"user_{user_id}"
            
            # 获取自定义元数据
            custom_metadata = doc_meta.get("metadata", {})
            
            # 获取所有切片文本
            chunks = []
            metadatas = []
            
            async for chunk in self.iter_chunks(user_id, document_id):
                chunks.append(chunk["content"])
                chunk_metadata = {
                    "document_id": document_id,
                    "chunk_index": chunk["chunk_index"],
                    "user_id": user_id,
                }
                
                # 只有当topic_path有值时才添加它
                if topic_path:
                    chunk_metadata["topic_path"] = topic_path
                
                # 添加自定义元数据以支持索引
                if custom_metadata:
                    # 从元数据中筛选索引字段
                    for key in ["title", "description", "tags", "category", "source", "author", "created_date"]:
                        if key in custom_metadata:
                            chunk_metadata[key] = custom_metadata[key]
                
                metadatas.append(chunk_metadata)
            
            if not chunks:
                raise ValueError(f"没有找到文档切片: {document_id}")
            
            # 使用collection_name添加向量
            result = await self.retriever.add(
                texts=chunks,
                collection_name=collection_name,
                user_id=user_id,
                metadatas=metadatas,
                indexable_fields=["title", "description", "tags", "category", "source", "author", "created_date"]
            )
            
            if not result.get("success", False):
                raise ValueError(f"向量添加失败: {result.get('error', '未知错误')}")
            
            # 确保创建索引
            await self.retriever.ensure_index(collection_name)
            
            return {
                "collection": collection_name,
                "vectors_count": result.get("added", 0),
                "success": True
            }
        except Exception as e:
            self.logger.error(f"生成嵌入向量失败: {e}")
            raise
    
    async def remove_vector_embeddings(self, user_id: str, document_id: str) -> bool:
        """从向量数据库中删除嵌入 - 支持自定义集合名称"""
        if not self.retriever:
            return False
        
        try:
            # 先获取文档元数据
            doc_meta = await self.meta_manager.get_metadata(user_id, document_id)
            if not doc_meta:
                return False
            
            # 获取保存的集合名称
            collection_name = doc_meta.get("collection_name")
            
            # 如果没有保存集合名称，尝试从主题路径提取
            if not collection_name and "topic_path" in doc_meta:
                collection_name = self.extract_collection_name_from_topic(user_id, doc_meta["topic_path"])
            
            # 如果仍然没有，使用默认命名
            if not collection_name:
                collection_name = f"user_{user_id}"
            
            # 从对应集合中删除
            result = await self.retriever.delete(
                collection_name=collection_name,
                user_id=user_id,
                document_id=document_id
            )
            return result.get("success", False)
        except Exception as e:
            self.logger.error(f"从向量存储删除失败: {e}")
            return False
    
    async def add_chunks_metadata(self, user_id: str, document_id: str, chunks: List[str]) -> bool:
        """添加切片数据到元数据 - 处理器直接了解切片内容"""
        chunks_data = [{"content": chunk, "metadata": {}} for chunk in chunks]
        result = await self.meta_manager.update_metadata(
            user_id, document_id,
            {"chunks": chunks_data}
        )
        return result is not None
    
    async def search_chunks(
        self, 
        user_id: str, 
        query: str, 
        document_id: str = None, 
        collection_name: str = None,
        limit: int = 10,
        threshold: float = 0.8
    ) -> Dict[str, Any]:
        """搜索文档内容 - 支持自定义集合名称"""
        if not query or not user_id:
            raise ValueError("无效的参数: 必须提供user_id和查询内容")
        
        if not self.retriever:
            raise ValueError("没有配置向量检索器，无法执行搜索")
        
        # 如果未提供集合名称，使用默认命名
        if not collection_name:
            collection_name = f"user_{user_id}"
        
        # 构建过滤条件
        filter_condition = None
        if document_id:
            filter_condition = f"document_id = '{document_id}'"
        
        # 使用retriever的query方法搜索
        results = await self.retriever.query(
            query_texts=query,
            collection_name=collection_name,
            user_id=user_id,
            document_id=document_id,
            limit=limit,
            threshold=threshold,
            filter=filter_condition
        )
        
        # 格式化结果
        if results and len(results) > 0:
            # 只处理第一个查询结果（因为只传入了一个查询）
            matches = results[0].get("results", [])
            
            # 增强结果 - 添加文档详细信息
            enhanced_matches = []
            for match in matches:
                doc_id = match["metadata"].get("document_id")
                if doc_id:
                    # 获取文档元数据
                    doc_meta = await self.meta_manager.get_metadata(user_id, doc_id)
                    if doc_meta:
                        match["document_meta"] = {
                            "title": doc_meta.get("original_name", ""),
                            "type": doc_meta.get("type", ""),
                            "state": doc_meta.get("state", ""),
                            "topic_path": doc_meta.get("topic_path", "")
                        }
                enhanced_matches.append(match)
            
            return {
                "query": query,
                "matches": enhanced_matches,
                "total": len(enhanced_matches),
                "collection": collection_name
            }
        else:
            # 没有结果或查询出错
            error = results[0].get("error") if results else "无匹配结果"
            if "error" in (results[0] if results else {}):
                raise ValueError(f"搜索失败: {error}")
            
            return {
                "query": query,
                "matches": [],
                "total": 0,
                "collection": collection_name
            }

    async def get_markdown(self, user_id: str, document_id: str) -> Dict[str, Any]:
        """获取文档的Markdown内容
        
        Args:
            user_id: 用户ID
            document_id: 文档ID
            
        Returns:
            包含Markdown内容和元数据的字典
            
        Raises:
            FileNotFoundError: 当Markdown文件不存在时
            ValueError: 当传入的参数无效时
        """
        if not user_id or not document_id:
            raise ValueError("用户ID和文档ID不能为空")
        
        # 获取Markdown文件路径
        md_path = self.get_md_path(user_id, document_id)
        
        # 检查文件是否存在
        if not md_path.exists():
            raise FileNotFoundError(f"找不到Markdown文件: {document_id}")
        
        try:
            # 读取Markdown内容
            async with aiofiles.open(md_path, 'r', encoding='utf-8') as f:
                content = await f.read()
            
            # 获取文件元数据
            file_stats = md_path.stat()
            
            return {
                "document_id": document_id,
                "content": content,
                "file_size": file_stats.st_size,
                "last_modified": int(file_stats.st_mtime),
                "file_path": str(md_path)
            }
        except Exception as e:
            self.logger.error(f"读取Markdown文件失败: {e}")
            raise

    def extract_collection_name_from_topic(self, user_id: str, topic_path: str) -> Optional[str]:
        """从主题路径中提取集合名称，并添加用户ID前缀防止冲突
        
        规则：找到由下划线包围的路径段，如 _category_/subcategory 取 user_123__category_
        
        Args:
            user_id: 用户ID
            topic_path: 主题路径，如 "finance/_reports_/q1" 或 "_finance_/reports"
            
        Returns:
            提取的集合名称，如无匹配则返回None
        """
        if not topic_path:
            return None
        
        # 安全检查
        if not user_id:
            return None
        
        # 按路径分隔符拆分
        parts = topic_path.split('/')
        
        # 查找符合"前后带下划线"规则的路径段
        for part in parts:
            if part.startswith('_') and part.endswith('_') and len(part) > 2:
                # 添加用户ID前缀避免冲突
                return f"user_{user_id}{part}"
            
        # 查找带下划线的连续路径段，如 '_finance/reports_'
        if '_' in topic_path:
            # 找到所有下划线的位置
            underscores = [i for i, char in enumerate(topic_path) if char == '_']
            if len(underscores) >= 2:
                # 检查第一个下划线是否在路径开头
                first_slash = topic_path.find('/')
                if first_slash == -1 or underscores[0] < first_slash:
                    # 查找匹配的结束下划线（在最后一个斜杠之后）
                    last_slash = topic_path.rfind('/')
                    for idx in underscores:
                        if idx > last_slash and last_slash != -1:
                            # 找到了符合条件的首尾下划线
                            collection_name = topic_path[underscores[0]:idx+1]
                            return f"user_{user_id}{collection_name}"
        
        return None

    async def list_user_collections(self, user_id: str) -> List[Dict[str, Any]]:
        """列出用户可访问的所有向量集合"""
        if not self.retriever:
            return []
        
        try:
            # 获取所有集合并添加日志
            all_collections = await self.retriever.list_collections()
            self.logger.info(f"获取到的所有集合: {all_collections}")
            
            # 筛选出用户可访问的集合
            user_collections = []
            default_collection = f"user_{user_id}"
            
            for collection in all_collections:
                # 检查是否为用户的默认集合或自定义集合
                if collection == default_collection or collection.startswith(f"user_{user_id}_"):
                    try:
                        # 获取集合统计信息
                        stats = await self.retriever.get_stats(collection)
                        
                        # 尝试提取主题名称
                        topic_name = None
                        if collection.startswith(f"user_{user_id}_"):
                            topic_name = collection[len(f"user_{user_id}"):]
                        
                        user_collections.append({
                            "collection_name": collection,
                            "topic_name": topic_name,
                            "vectors_count": stats.get(collection, {}).get("total_vectors", 0),
                            "document_count": stats.get(collection, {}).get("unique_documents", 0)
                        })
                    except Exception as e:
                        self.logger.error(f"获取集合{collection}统计信息失败: {e}")
                        # 添加基本信息，避免完全跳过
                        user_collections.append({
                            "collection_name": collection,
                            "topic_name": collection.replace(f"user_{user_id}", "") if collection.startswith(f"user_{user_id}_") else None,
                            "vectors_count": 0,
                            "document_count": 0
                        })
            
            self.logger.info(f"为用户 {user_id} 找到的集合: {[c['collection_name'] for c in user_collections]}")
            return user_collections
        except Exception as e:
            self.logger.error(f"获取用户集合失败: {e}")
            return []

    async def update_document_summary_vector(
        self,
        user_id: str,
        document_id: str,
        summary: str,
        doc_meta: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """更新文档摘要向量
        
        Args:
            user_id: 用户ID
            document_id: 文档ID
            summary: 文档摘要
            doc_meta: 文档元数据(可选)，如果不提供将自动获取
            
        Returns:
            字典，包含操作结果
        """
        if not self.retriever:
            return {"success": False, "error": "未配置向量数据库"}
        
        try:
            # 获取文档元数据(如果未提供)
            if not doc_meta:
                doc_meta = await self.meta_manager.get_metadata(user_id, document_id)
                if not doc_meta:
                    return {"success": False, "error": f"找不到文档: {document_id}"}
            
            # 固定使用summaries集合
            collection_name = "summaries"
            
            # 创建向量元数据
            vector_metadata = {
                "document_id": document_id,
                "user_id": user_id,
                "is_public": doc_meta.get("is_public", False),
                "allowed_roles": doc_meta.get("allowed_roles", []),
                "title": doc_meta.get("title") or doc_meta.get("original_name", ""),
                "topic_path": doc_meta.get("topic_path", "")
            }
            
            # 添加向量 - 使用document_id作为向量ID以便更新
            result = await self.retriever.add(
                texts=[summary],
                collection_name=collection_name,
                metadatas=[vector_metadata],
                ids=[document_id]
            )
            
            return {
                "success": result.get("success", False),
                "collection": collection_name,
                "document_id": document_id
            }
        except Exception as e:
            self.logger.error(f"更新摘要向量失败: {e}")
            return {"success": False, "error": str(e)}

    async def remove_summary_vector(self, user_id: str, document_id: str) -> bool:
        """从summaries集合中删除文档摘要向量
        
        Args:
            user_id: 用户ID
            document_id: 文档ID
            
        Returns:
            布尔值，表示操作是否成功
        """
        if not self.retriever:
            return False
        
        try:
            # 固定使用summaries集合
            collection_name = "summaries"
            
            # 从摘要集合中删除
            result = await self.retriever.delete(
                collection_name=collection_name,
                user_id=user_id,
                document_id=document_id  # 文档ID直接作为向量ID使用
            )
            
            if result.get("success", True):
                self.logger.info(f"已从摘要集合中删除文档 {document_id} 的向量")
                return True
            else:
                self.logger.warning(f"从摘要集合删除失败: {result.get('error', '未知错误')}")
                return False
        except Exception as e:
            self.logger.error(f"删除摘要向量失败: {e}")
            return False

    async def process_document_complete(self, user_id: str, document_id: str) -> Dict[str, Any]:
        """一步完成文档处理：转换、切片和嵌入向量
        
        Args:
            user_id: 用户ID
            document_id: 文档ID
            
        Returns:
            包含处理结果的字典
        """
        try:
            # 1. 获取文档元数据
            doc_meta = await self.meta_manager.get_metadata(user_id, document_id)
            if not doc_meta:
                raise ValueError(f"找不到文档元数据: {document_id}")
            
            # 从元数据中获取主题路径和确定集合名称
            topic_path = doc_meta.get("topic_path", "")
            collection_name = None
            
            # 从主题路径提取集合名称
            if topic_path:
                extracted_collection = self.extract_collection_name_from_topic(user_id, topic_path)
                if extracted_collection:
                    collection_name = extracted_collection
            
            # 如果没有提取到集合名称，使用默认命名
            if not collection_name:
                collection_name = f"user_{user_id}"
            
            # 2. 直接转换为Markdown
            try:
                # 不保存文件，直接获取转换结果
                markdown_result = await self.convert_to_markdown(user_id, document_id)
                md_content = markdown_result["content"]
                
                if not md_content.strip():
                    raise ValueError("转换后的文档内容为空")
                
            except Exception as e:
                self.logger.error(f"转换Markdown失败: {e}")
                # 更新元数据，标记为处理失败
                await self.meta_manager.update_metadata(
                    user_id, document_id, 
                    {
                        "processed": False,
                        "process_error": f"转换失败: {str(e)}"
                    }
                )
                raise
            
            # 3. 直接在内存中切片
            try:
                # 简单分段策略
                chunks = []
                current_chunk = ""
                for line in md_content.split('\n'):
                    current_chunk += line + '\n'
                    if len(current_chunk) > 1000 or (line.startswith('#') and current_chunk.strip() != line):
                        chunks.append(current_chunk.strip())
                        current_chunk = ""
                
                # 添加最后一个块
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                
                if not chunks:
                    raise ValueError("文档内容为空，切片失败")
                
            except Exception as e:
                self.logger.error(f"文档切片失败: {e}")
                # 更新元数据，标记为处理失败
                await self.meta_manager.update_metadata(
                    user_id, document_id, 
                    {
                        "processed": False,
                        "process_error": f"切片失败: {str(e)}"
                    }
                )
                raise
            
            # 4. 直接生成向量嵌入
            try:
                if not self.retriever:
                    raise ValueError("没有配置向量检索器，无法生成嵌入")
                
                # 获取自定义元数据
                custom_metadata = doc_meta.get("metadata", {})
                
                # 准备向量数据
                metadatas = []
                
                for i, chunk in enumerate(chunks):
                    chunk_metadata = {
                        "document_id": document_id,
                        "chunk_index": i,
                        "user_id": user_id,
                    }
                    
                    # 只有当topic_path有值时才添加它
                    if topic_path:
                        chunk_metadata["topic_path"] = topic_path
                    
                    # 添加自定义元数据以支持索引
                    if custom_metadata:
                        # 从元数据中筛选索引字段
                        for key in ["title", "description", "tags", "category", "source", "author", "created_date"]:
                            if key in custom_metadata:
                                chunk_metadata[key] = custom_metadata[key]
                    
                    metadatas.append(chunk_metadata)
                
                # 使用collection_name添加向量
                result = await self.retriever.add(
                    texts=chunks,
                    collection_name=collection_name,
                    user_id=user_id,
                    metadatas=metadatas,
                    indexable_fields=["title", "description", "tags", "category", "source", "author", "created_date"],
                    ids=[f"{document_id}_{i}" for i in range(len(chunks))]
                )
                
                if not result.get("success", False):
                    raise ValueError(f"向量添加失败: {result.get('error', '未知错误')}")
                
                # 确保创建索引
                await self.retriever.ensure_index(collection_name)
                
            except Exception as e:
                self.logger.error(f"生成嵌入向量失败: {e}")
                # 更新元数据，标记为处理失败
                await self.meta_manager.update_metadata(
                    user_id, document_id, 
                    {
                        "processed": False,
                        "process_error": f"嵌入失败: {str(e)}"
                    }
                )
                raise
            
            # 5. 更新元数据，标记为已处理
            update_result = await self.meta_manager.update_metadata(
                user_id, document_id, 
                {
                    "processed": True,
                    "collection_name": collection_name,
                    "process_error": None  # 清除可能存在的错误信息
                }
            )
            
            return {
                "document_id": document_id,
                "collection": collection_name,
                "chunks_count": len(chunks),
                "vectors_count": result.get("added", 0),
                "success": True
            }
        except Exception as e:
            self.logger.error(f"文档处理失败: {e}")
            # 更新元数据，标记为处理失败
            await self.meta_manager.update_metadata(
                user_id, document_id, 
                {
                    "processed": False,
                    "process_error": str(e)
                }
            )
            raise