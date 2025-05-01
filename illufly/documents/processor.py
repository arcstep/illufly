import os
import shutil
import uuid
import time
import aiofiles
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, AsyncGenerator
from fastapi import UploadFile
from voidrail import ClientDealer

from ..llm import LanceRetriever

class DocumentProcessor:
    """处理文档转换的专用类 - 专注于文档处理的具体实现"""
    
    def __init__(
        self, 
        docs_dir: str, 
        meta_manager,
        max_file_size: int = 50 * 1024 * 1024, 
        allowed_extensions: List[str] = None,
        voidrail_client: ClientDealer = None,
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
        self.voidrail_client = voidrail_client
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
    
    # ==== 文档处理核心方法 ====
    
    async def save_uploaded_file(self, user_id: str, file: UploadFile) -> Dict[str, Any]:
        """保存上传的文件并返回基本信息"""
        # 检查文件类型
        if not self.is_valid_file_type(file.filename):
            raise ValueError(f"不支持的文件类型: {file.filename}")
        
        # 生成文档ID和路径
        document_id = self.generate_document_id(file.filename)
        # 确保目录存在
        self.ensure_raw_dir(user_id)
        file_path = self.get_raw_path(user_id, document_id)
        
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
        document_id = self.generate_document_id(filename)
        
        # 返回基本信息
        return {
            "document_id": document_id,
            "original_name": filename,
            "source_type": "remote",
            "source_url": url,
            "type": self.get_file_type(filename),
            "extension": self.get_file_extension(filename)
        }
    
    async def convert_to_markdown(self, user_id: str, document_id: str, voidrail_client=None) -> Dict[str, Any]:
        """将文档转换为Markdown格式"""
        doc_path = self.get_raw_path(user_id, document_id)
        
        # 确保目录存在
        self.ensure_md_dir(user_id)
        md_path = self.get_md_path(user_id, document_id)
        
        # 检查原始文档是否存在
        if not doc_path.exists():
            raise FileNotFoundError(f"找不到原始文档: {document_id}")
        
        try:
            # 调用voidrail进行转换
            if voidrail_client:
                # 使用LLM服务转换
                markdown_content = ""
                async for chunk in voidrail_client.stream(task="file_to_markdown", file_path=str(doc_path)):
                    markdown_content += chunk
                
                # 保存Markdown文件
                async with aiofiles.open(md_path, 'w', encoding='utf-8') as f:
                    await f.write(markdown_content)
            else:
                # 简单转换(仅用于测试)
                markdown_content = f"# {document_id}\n\n自动生成的Markdown内容"
                async with aiofiles.open(md_path, 'w', encoding='utf-8') as f:
                    await f.write(markdown_content)
            
            return {
                "md_path": str(md_path),
                "content_preview": markdown_content[:200] + "...",
                "success": True
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
            result = await self.convert_to_markdown(user_id, document_id, voidrail_client=self.voidrail_client)
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
        """生成向量嵌入 - 正确使用LanceRetriever的add方法"""
        if not self.retriever:
            raise ValueError("没有配置向量检索器，无法生成嵌入")
        
        try:
            # 获取所有切片文本
            chunks = []
            metadatas = []
            
            async for chunk in self.iter_chunks(user_id, document_id):
                chunks.append(chunk["content"])
                metadatas.append({
                    "document_id": document_id,
                    "chunk_index": chunk["chunk_index"],
                    "user_id": user_id
                })
            
            if not chunks:
                raise ValueError(f"没有找到文档切片: {document_id}")
            
            # 使用retriever的add方法添加向量
            collection_name = f"user_{user_id}"
            result = await self.retriever.add(
                texts=chunks,
                collection_name=collection_name,
                user_id=user_id,
                metadatas=metadatas
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
        """从向量数据库中删除嵌入 - 正确使用LanceRetriever的delete方法"""
        if not self.retriever:
            return False
        
        try:
            collection_name = f"user_{user_id}"
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
    
    async def update_document_metadata(
        self,
        user_id: str,
        document_id: str,
        metadata_updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """更新文档元数据中与处理相关的字段"""
        return await self.meta_manager.update_metadata(
            user_id, document_id, metadata_updates
        )

    async def search_chunks(
        self, 
        user_id: str, 
        query: str, 
        document_id: str = None, 
        limit: int = 10,
        threshold: float = 0.8
    ) -> Dict[str, Any]:
        """搜索文档内容 - 使用向量检索进行语义搜索"""
        if not query or not user_id:
            raise ValueError("无效的参数: 必须提供user_id和查询内容")
        
        if not self.retriever:
            raise ValueError("没有配置向量检索器，无法执行搜索")
        
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
                        }
                enhanced_matches.append(match)
            
            return {
                "query": query,
                "matches": enhanced_matches,
                "total": len(enhanced_matches)
            }
        else:
            # 没有结果或查询出错
            error = results[0].get("error") if results else "无匹配结果"
            if "error" in (results[0] if results else {}):
                raise ValueError(f"搜索失败: {error}")
            
            return {
                "query": query,
                "matches": [],
                "total": 0
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