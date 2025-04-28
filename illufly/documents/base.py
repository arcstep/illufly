from typing import List, Dict, Any, Optional, AsyncGenerator, Literal
from pathlib import Path
import os
import shutil
import uuid
import time
import aiofiles
import logging
import mimetypes
import asyncio
import json
from fastapi import UploadFile
from voidrail import ClientDealer
from ..llm.retriever.lancedb import LanceRetriever
from .status import DocumentStatus, ProcessStage, DocumentProcessInfo

logger = logging.getLogger(__name__)

class DocumentService:
    """文档管理服务
    
    基于约定的文件组织结构：
    - {user_id}/raw/{document_id} - 原始文件
    - {user_id}/md/{document_id}.md - Markdown文件
    - {user_id}/chunks/{document_id}/ - 切片目录
    - {user_id}/meta/{document_id}.json - 元数据
    """
    
    def __init__(
        self, 
        base_dir: str, 
        max_file_size: int = 50 * 1024 * 1024,  # 默认50MB 
        max_total_size_per_user: int = 200 * 1024 * 1024,  # 默认200MB
        allowed_extensions: List[str] = None,
        voidrail_client: ClientDealer = None,
        retriever: LanceRetriever = None,
        max_versions: int = 5
    ):
        """初始化文档管理服务"""
        self.base_dir = Path(base_dir)
        self.temp_dir = self.base_dir / "temp"
        
        # 创建基础目录
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_file_size = max_file_size
        self.max_total_size_per_user = max_total_size_per_user
        self.allowed_extensions = allowed_extensions or [
            '.pptx',
            '.md', '.markdown',
            '.pdf', '.docx', '.txt',
            '.jpg', '.jpeg', '.png', '.gif', '.webp'
        ]
        
        # 文件MIME类型映射
        self._mime_types = {
            '.pdf': 'application/pdf',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.txt': 'text/plain',
            '.md': 'text/markdown',
            '.markdown': 'text/markdown',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }

        self.voidrail_client = voidrail_client or ClientDealer(router_address="tcp://127.0.0.1:31571")
        # 向量检索器实例（用于索引和搜索）
        self.retriever = retriever or LanceRetriever(
            output_dir=os.path.join(str(self.base_dir), "vector_db")
        )
        # 文件版本管理：覆盖前最多保留 max_versions 个旧版本
        self.max_versions = max_versions

    def default_indexing_collection(self, user_id: str) -> str:
        """获取默认集合名称"""
        return f"user_{user_id}"
    
    # 目录管理函数
    def get_user_dir(self, user_id: str, subdir: str) -> Path:
        """获取用户指定子目录"""
        user_dir = self.base_dir / user_id / subdir
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir
    
    # 路径获取函数
    def get_raw_path(self, user_id: str, document_id: str) -> Path:
        """获取原始文件路径"""
        return self.get_user_dir(user_id, "raw") / document_id
    
    def get_md_path(self, user_id: str, document_id: str) -> Path:
        """获取Markdown文件路径"""
        return self.get_user_dir(user_id, "md") / f"{document_id}.md"
    
    def get_chunks_dir(self, user_id: str, document_id: str) -> Path:
        """获取切片目录路径"""
        chunks_dir = self.get_user_dir(user_id, "chunks") / document_id
        chunks_dir.mkdir(exist_ok=True)
        return chunks_dir
    
    def get_meta_path(self, user_id: str, document_id: str) -> Path:
        """获取元数据文件路径"""
        return self.get_user_dir(user_id, "meta") / f"{document_id}.json"
    
    def get_backup_dir(self, user_id: str, subdir: str, document_id: str) -> Path:
        """获取用于该文档版本备份的目录"""
        bd = self.base_dir / user_id / "backups" / subdir / document_id
        bd.mkdir(parents=True, exist_ok=True)
        return bd

    def _rotate_backup(self, user_id: str, subdir: str, document_id: str, file_path: Path):
        """备份旧文件并只保留最新 self.max_versions 个"""
        if not file_path.exists():
            return
        bkdir = self.get_backup_dir(user_id, subdir, document_id)
        ts = int(time.time())
        bkp = bkdir / f"{file_path.name}.{ts}"
        shutil.copy2(file_path, bkp)
        # 清理多余历史版本
        versions = sorted(bkdir.glob(f"{file_path.name}.*"), key=lambda p: p.name)
        while len(versions) > self.max_versions:
            versions.pop(0).unlink()

    def generate_document_id(self, original_filename: str = None) -> str:
        """生成文档ID"""
        if original_filename:
            _, ext = os.path.splitext(original_filename)
            return f"{uuid.uuid4().hex}{ext.lower()}"
        return uuid.uuid4().hex
    
    async def document_exists(self, user_id: str, document_id: str) -> bool:
        """检查文档是否存在且活跃"""
        meta_path = self.get_meta_path(user_id, document_id)
        if not meta_path.exists():
            return False
            
        try:
            doc_meta = await self.get_document_meta(user_id, document_id)
            if not doc_meta or doc_meta.get("status") != DocumentStatus.ACTIVE:
                return False
                
            if doc_meta.get("source_type") == "local":
                raw_path = self.get_raw_path(user_id, document_id)
                if not raw_path.exists():
                    return False
                    
            return True
        except Exception as e:
            logger.error(f"检查文档存在性失败: {user_id}/{document_id}, 错误: {e}")
            return False
    
    async def save_document(
        self, 
        user_id: str, 
        file: UploadFile,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """保存上传的文档"""
        # 检查文件类型
        if not self.is_valid_file_type(file.filename):
            raise ValueError(f"不支持的文件类型: {file.filename}")
        
        # 检查存储空间
        current_usage = await self.calculate_storage_usage(user_id)
        
        # 生成文档ID和路径
        document_id = self.generate_document_id(file.filename)
        file_path = self.get_raw_path(user_id, document_id)
        meta_path = self.get_meta_path(user_id, document_id)
        
        # 覆盖前备份 raw 文件
        self._rotate_backup(user_id, "raw", document_id, file_path)
        
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
        
        # 检查总存储空间
        if current_usage + file_size > self.max_total_size_per_user:
            os.remove(file_path)
            raise ValueError(f"用户存储空间不足，已使用 {current_usage} bytes，限制 {self.max_total_size_per_user} bytes")
        
        # 创建元数据 - 使用新的处理信息类
        now = time.time()
        process_info = DocumentProcessInfo(current_stage=ProcessStage.READY)
        
        doc_meta = {
            "document_id": document_id,
            "original_name": file.filename,
            "size": file_size,
            "type": self.get_file_type(file.filename),
            "extension": self.get_file_extension(file.filename),
            "source_type": "local",
            "created_at": now,
            "updated_at": now,
            "status": DocumentStatus.ACTIVE,
            "process": process_info.to_dict()
        }
        
        # 添加额外元数据
        if metadata:
            # 避免覆盖核心字段
            for key in ["document_id", "created_at", "process", "status"]:
                if key in metadata:
                    del metadata[key]
            doc_meta.update(metadata)
        
        # 覆盖前备份 meta 文件
        self._rotate_backup(user_id, "meta", document_id, meta_path)
        async with aiofiles.open(meta_path, 'w') as meta_file:
            await meta_file.write(json.dumps(doc_meta, ensure_ascii=False))
        
        return doc_meta
    
    async def create_remote_document(
        self,
        user_id: str,
        url: str,
        filename: str,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """创建远程文档引用"""
        document_id = self.generate_document_id(filename)
        meta_path = self.get_meta_path(user_id, document_id)
        
        # 创建元数据 - 使用新的处理信息类
        now = time.time()
        process_info = DocumentProcessInfo(current_stage=ProcessStage.READY)
        
        doc_meta = {
            "document_id": document_id,
            "original_name": filename,
            "size": 0,  # 未知
            "type": self.get_file_type(filename),
            "extension": self.get_file_extension(filename),
            "source_type": "remote",
            "source_url": url,
            "created_at": now,
            "updated_at": now,
            "status": DocumentStatus.ACTIVE,
            "process": process_info.to_dict()
        }
        
        # 添加额外元数据
        if metadata:
            # 避免覆盖核心字段
            for key in ["document_id", "created_at", "process", "status"]:
                if key in metadata:
                    del metadata[key]
            doc_meta.update(metadata)
        
        # 保存元数据
        async with aiofiles.open(meta_path, 'w') as meta_file:
            await meta_file.write(json.dumps(doc_meta, ensure_ascii=False))
        
        return doc_meta
    
    async def save_markdown(
        self, 
        user_id: str, 
        document_id: str, 
        markdown_content: str = None
    ) -> Dict[str, Any]:
        """保存文档的Markdown版本"""
        try:
            # 检查文档是否存在
            if not await self.document_exists(user_id, document_id):
                raise FileNotFoundError(f"文档不存在: {document_id}")
            
            # 获取文档元数据
            doc_meta = await self.get_document_meta(user_id, document_id)
            source_type = doc_meta.get("source_type", "local")
            
            # 获取markdown文件路径
            md_path = self.get_md_path(user_id, document_id)
            
            # 更新处理阶段为转换中
            await self.update_process_stage(
                user_id, document_id, "conversion", 
                {"stage": ProcessStage.CONVERTING, "started_at": time.time()}
            )

            # 转换markdown内容
            if markdown_content is None:
                markdown_content = ""  # 初始化为空字符串
                
                # 根据文档源类型处理
                if source_type == "remote":
                    # 远程文档：直接使用URL
                    source_url = doc_meta.get("source_url")
                    if not source_url:
                        raise ValueError("远程文档缺少URL")
                    
                    # 调用服务处理网页内容
                    resp = self.voidrail_client.stream(
                        method="SimpleDocling.convert",
                        timeout=600,
                        content=source_url,
                        content_type="url"
                    )
                else:
                    # 本地文档：读取文件并base64编码
                    raw_path = self.get_raw_path(user_id, document_id)
                    
                    # 读取文件内容并转为base64编码
                    import base64
                    async with aiofiles.open(raw_path, "rb") as f:
                        file_content = await f.read()
                        encoded_content = base64.b64encode(file_content).decode("utf-8")
                    
                    # 调用服务
                    resp = self.voidrail_client.stream(
                        method="SimpleDocling.convert",
                        timeout=600,
                        content=encoded_content,
                        content_type="base64",
                        file_type=doc_meta.get("extension", "").lstrip('.')  # 从元数据获取文件类型
                    )
                
                # 收集转换结果
                async for chunk in resp:
                    markdown_content += chunk

            # 保存前备份 md 文件
            self._rotate_backup(user_id, "md", document_id, md_path)
            async with aiofiles.open(md_path, 'w', encoding='utf-8') as f:
                await f.write(markdown_content)
            
            # 计算标题数量以评估文档结构
            import re
            headers_count = len(re.findall(r'^#{1,6}\s+.+$', markdown_content, re.MULTILINE))
            paragraphs_count = len(re.split(r'\n\s*\n', markdown_content))
            
            # 更新为已转换
            now = time.time()
            await self.update_process_stage(
                user_id, document_id, "conversion", 
                {
                    "stage": ProcessStage.CONVERTED,
                    "success": True,
                    "finished_at": now,
                    "details": {
                        "content_length": len(markdown_content),
                        "headers_count": headers_count,
                        "paragraphs_count": paragraphs_count
                    }
                }
            )
            
            # 覆盖元数据前先备份
            self._rotate_backup(user_id, "meta", document_id, self.get_meta_path(user_id, document_id))
            await self.update_metadata(user_id, document_id, {
                "markdown": {
                    "path": str(md_path),
                    "length": len(markdown_content),
                    "structure": {
                        "headers": headers_count,
                        "paragraphs": paragraphs_count
                    },
                    "updated_at": now
                },
                "process": {"current_stage": ProcessStage.CONVERTED}
            })

        except Exception as e:
            # 更新为转换失败
            await self.update_process_stage(
                user_id, document_id, "conversion", 
                {
                    "stage": ProcessStage.FAILED,
                    "success": False,
                    "error": str(e),
                    "finished_at": time.time()
                }
            )

        finally:
            return await self.get_document_meta(user_id, document_id)

    async def save_chunks(
        self, 
        user_id: str, 
        document_id: str, 
        chunks: List[Dict[str, Any]] = None
    ) -> bool:
        """保存文档的切片
        
        Args:
            user_id: 用户ID
            document_id: 文档ID
            chunks: 可选，文档切片列表。如果不提供，将使用默认切片方法生成
            
        Returns:
            bool: 保存成功返回True，失败返回False
        """
        try:
            # 检查文档是否存在
            if not await self.document_exists(user_id, document_id):
                raise FileNotFoundError(f"文档不存在: {document_id}")
            
            # 先删除旧的 chunks 目录，避免残留
            dir0 = self.base_dir / user_id / "chunks" / document_id
            if dir0.exists():
                shutil.rmtree(dir0)
            chunks_dir = self.get_chunks_dir(user_id, document_id)
            
            # 更新处理阶段为切片中
            await self.update_process_stage(
                user_id, document_id, "chunking", 
                {"stage": ProcessStage.CHUNKING, "started_at": time.time()}
            )
            
            # 如果未提供切片，则使用默认切片方法生成
            if chunks is None:
                # 获取文档元数据
                doc_meta = await self.get_document_meta(user_id, document_id)
                
                # 确保文档已转换为Markdown
                conversion_stage = doc_meta.get("process", {}).get("stages", {}).get("conversion", {})
                if conversion_stage.get("stage") != ProcessStage.CONVERTED:
                    raise ValueError(f"文档必须先转换为Markdown才能切片: {document_id}")
                
                # 读取Markdown内容
                markdown_content = await self.get_markdown(user_id, document_id)
                
                # 导入切片器
                from .chunker import get_chunker
                
                # 创建文档类型对应的切片器
                chunker = get_chunker(
                    doc_type=doc_meta.get("type", "markdown"),
                    max_chunk_size=4000,  # 默认最大切片大小
                    overlap=200  # 默认重叠大小
                )
                
                # 生成切片
                chunks = await chunker.chunk_document(
                    content=markdown_content,
                    metadata={
                        "document_id": document_id,
                        "title": doc_meta.get("title", ""),
                        "document_type": doc_meta.get("type", "")
                    }
                )
            
            # 保存每个切片
            chunks_meta = []
            for i, chunk in enumerate(chunks):
                # 构建文件路径，使用固定位数便于排序
                chunk_filename = f"chunk_{i:06d}.txt"
                chunk_path = chunks_dir / chunk_filename
                
                # 获取内容
                content = chunk.get("text") or chunk.get("content")
                if not content:
                    logger.error(f"切片内容缺失: {chunk}")
                    continue
                    
                # 保存内容
                async with aiofiles.open(chunk_path, 'w', encoding='utf-8') as f:
                    await f.write(content)
                
                # 记录切片元数据
                chunk_meta = {
                    "index": i,
                    "path": str(chunk_path),
                    "next_index": i + 1 if i < len(chunks) - 1 else None,
                    "prev_index": i - 1 if i > 0 else None
                }
                
                # 添加原始元数据
                if "metadata" in chunk:
                    chunk_meta["metadata"] = chunk["metadata"]
                    
                # 添加标题信息（如果有）
                if "title" in chunk:
                    chunk_meta["title"] = chunk["title"]
                    
                chunks_meta.append(chunk_meta)
            
            # 更新为已切片
            now = time.time()
            
            # 准备切片统计信息
            chunks_stats = {
                "count": len(chunks),
                "avg_length": sum(len(chunk.get("text") or chunk.get("content", "")) for chunk in chunks) // len(chunks) if chunks else 0,
                "titles": [chunk.get("title", "") for chunk in chunks if "title" in chunk]
            }
            
            await self.update_metadata(user_id, document_id, {
                "chunks": chunks_meta,
                "chunks_count": len(chunks),
                "chunks_stats": chunks_stats,
                "process": {
                    "current_stage": ProcessStage.CHUNKED,
                    "stages": {
                        "chunking": {
                            "stage": ProcessStage.CHUNKED,
                            "success": True,
                            "finished_at": now,
                            "details": {
                                "chunks_count": len(chunks),
                                "avg_chunk_length": chunks_stats["avg_length"]
                            }
                        }
                    }
                }
            })
            
            return True
        
        except Exception as e:
            # 更新为切片失败
            await self.update_process_stage(
                user_id, document_id, "chunking", 
                {
                    "stage": ProcessStage.FAILED,
                    "success": False,
                    "error": str(e),
                    "finished_at": time.time()
                }
            )
            return False
    
    async def get_markdown(self, user_id: str, document_id: str) -> str:
        """获取文档的Markdown内容"""
        # 检查文档是否存在
        if not await self.document_exists(user_id, document_id):
            raise FileNotFoundError(f"文档不存在: {document_id}")
        
        # 获取元数据
        doc_meta = await self.get_document_meta(user_id, document_id)
        
        # 检查是否已转换为Markdown
        conversion_stage = doc_meta.get("process", {}).get("stages", {}).get("conversion", {})
        if conversion_stage.get("stage") != ProcessStage.CONVERTED:
            raise FileNotFoundError(f"该文档尚未转换为Markdown: {document_id}")
        
        # 读取Markdown文件
        md_path = self.get_md_path(user_id, document_id)
        if not md_path.exists():
            raise FileNotFoundError(f"Markdown文件不存在: {md_path}")
        
        try:
            async with aiofiles.open(md_path, 'r', encoding='utf-8') as f:
                return await f.read()
        except Exception as e:
            logger.error(f"读取Markdown内容失败: {md_path}, 错误: {e}")
            raise FileNotFoundError(f"无法读取Markdown内容: {str(e)}")
    
    async def iter_chunks(
        self, 
        user_id: str,
        document_id: str = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """迭代文档切片内容"""
        if document_id:
            # 获取指定文档的切片
            doc_meta = await self.get_document_meta(user_id, document_id)
            if not doc_meta:
                return
            
            # 检查是否有切片
            chunking_stage = doc_meta.get("process", {}).get("stages", {}).get("chunking", {})
            if chunking_stage.get("stage") != ProcessStage.CHUNKED:
                return
            
            # 准备文档基本元数据
            doc_info = {
                "document_id": doc_meta["document_id"],
                "title": doc_meta.get("title", ""),
                "original_name": doc_meta.get("original_name", ""),
                "type": doc_meta.get("type", ""),
                "created_at": doc_meta.get("created_at"),
                "extension": doc_meta.get("extension", "")
            }
            
            # 读取切片
            for chunk_meta in doc_meta.get("chunks", []):
                try:
                    chunk_path = Path(chunk_meta["path"])
                    if not chunk_path.exists():
                        continue
                        
                    async with aiofiles.open(chunk_path, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        
                        chunk_data = {
                            "document_id": document_id,
                            "chunk_index": chunk_meta["index"],
                            "content": content,
                            "document": doc_info
                        }
                        
                        # 添加切片元数据
                        if "metadata" in chunk_meta:
                            chunk_data["metadata"] = chunk_meta["metadata"]
                        else:
                            chunk_data["metadata"] = {}
                            
                        # 添加标题信息（如果有）
                        if "title" in chunk_meta:
                            chunk_data["title"] = chunk_meta["title"]
                            
                        yield chunk_data
                except Exception as e:
                    logger.error(f"读取切片内容失败: {chunk_path}, 错误: {e}")
        else:
            # 所有文档的切片
            docs = await self.list_documents(user_id)
            for doc in docs:
                async for chunk in self.iter_chunks(user_id, doc["document_id"]):
                    yield chunk
    
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
    
    async def delete_document(self, user_id: str, document_id: str) -> bool:
        """删除文档及相关资源"""
        doc_meta = await self.get_document_meta(user_id, document_id)
        if not doc_meta:
            logger.warning(f"尝试删除不存在的文档: {document_id}")
            return False
        # 先从向量索引中删除，保证一致性
        try:
            coll = self.default_indexing_collection(user_id)
            await self.retriever.delete(
                collection_name=coll,
                user_id=user_id,
                document_id=document_id
            )
        except Exception as e:
            logger.error(f"删除向量索引失败: {e}")

        success = True
        # 1. 删除原始文件
        raw_path = self.get_raw_path(user_id, document_id)
        if raw_path.exists():
            try:
                os.remove(raw_path)
            except Exception as e:
                logger.error(f"删除原始文件失败: {raw_path}, 错误: {e}")
                success = False
        
        # 2. 删除Markdown文件
        md_path = self.get_md_path(user_id, document_id)
        if md_path.exists():
            try:
                os.remove(md_path)
            except Exception as e:
                logger.error(f"删除Markdown文件失败: {md_path}, 错误: {e}")
                success = False
        
        # 3. 删除切片目录
        chunks_dir = self.get_chunks_dir(user_id, document_id)
        if chunks_dir.exists():
            try:
                shutil.rmtree(chunks_dir)
            except Exception as e:
                logger.error(f"删除切片目录失败: {chunks_dir}, 错误: {e}")
                success = False
        
        # 4. 最后才删除元数据
        meta_path = self.get_meta_path(user_id, document_id)
        if meta_path.exists():
            try:
                os.remove(meta_path)
            except Exception as e:
                logger.error(f"删除元数据失败: {meta_path}, 错误: {e}")
                success = False
        
        return success
    
    async def list_documents(self, user_id: str) -> List[Dict[str, Any]]:
        """列出用户的所有文档"""
        meta_dir = self.get_user_dir(user_id, "meta")
        docs = []
        
        for meta_path in meta_dir.glob("*.json"):
            try:
                async with aiofiles.open(meta_path, 'r') as f:
                    content = await f.read()
                    doc_meta = json.loads(content)
                    
                    # 只返回活跃文档
                    if doc_meta.get("status") == DocumentStatus.ACTIVE:
                        docs.append(doc_meta)
            except Exception as e:
                logger.error(f"读取文档元数据失败: {meta_path}, 错误: {e}")
        
        # 按创建时间降序排序
        docs.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return docs
    
    async def get_document_meta(self, user_id: str, document_id: str) -> Optional[Dict[str, Any]]:
        """获取文档元数据"""
        meta_path = self.get_meta_path(user_id, document_id)
        
        if not meta_path.exists():
            return None
        
        try:
            async with aiofiles.open(meta_path, 'r') as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            logger.error(f"读取文档元数据失败: {meta_path}, 错误: {e}")
            return None
    
    async def update_metadata(self, user_id: str, document_id: str, metadata: Dict[str, Any]) -> bool:
        """更新文档元数据"""
        try:
            meta_path = self.get_meta_path(user_id, document_id)
            
            # 读取现有元数据
            doc_meta = {}
            if meta_path.exists():
                async with aiofiles.open(meta_path, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    if content:
                        doc_meta = json.loads(content)
            
            # 递归合并函数
            def deep_update(d, u):
                for k, v in u.items():
                    if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                        deep_update(d[k], v)
                    else:
                        d[k] = v
            
            # 递归合并元数据
            deep_update(doc_meta, metadata)
            
            # 强制更新关键字段
            doc_meta["updated_at"] = time.time()
            
            # 写入更新后的元数据
            async with aiofiles.open(meta_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(doc_meta, ensure_ascii=False))
            
            return True
        except Exception as e:
            logger.error(f"更新元数据失败: {str(e)}")
            return False
    
    async def update_process_stage(
        self, 
        user_id: str, 
        document_id: str, 
        stage_name: Literal["conversion", "chunking", "embedding"],
        stage_data: Dict[str, Any]
    ) -> bool:
        """更新文档处理阶段状态"""
        try:
            # 获取当前处理信息
            doc_meta = await self.get_document_meta(user_id, document_id)
            if not doc_meta:
                return False
                
            process_data = doc_meta.get("process", {})
            process_info = DocumentProcessInfo.from_dict(process_data)
            
            # 更新阶段状态
            process_info.update_stage(stage_name, stage_data)
            
            # 保存更新后的处理信息
            await self.update_metadata(user_id, document_id, {
                "process": process_info.to_dict()
            })
            
            return True
        except Exception as e:
            logger.error(f"更新处理阶段失败: {e}")
            return False
    
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
    
    def get_file_mimetype(self, file_name: str) -> str:
        """获取文件MIME类型"""
        _, ext = os.path.splitext(file_name)
        mime_type = self._mime_types.get(ext.lower())
        if not mime_type:
            # 使用系统mimetypes库猜测
            mime_type = mimetypes.guess_type(file_name)[0]
        return mime_type or 'application/octet-stream'

    async def create_document_index(self, user_id: str, document_id: str) -> bool:
        """将文档切片添加到向量索引"""
        # 检查文档是否存在
        if not await self.document_exists(user_id, document_id):
            logger.error(f"文档不存在: {document_id}")
            return False
        
        # 获取文档元数据
        doc_meta = await self.get_document_meta(user_id, document_id)
        
        # 检查是否已切片
        chunking_stage = doc_meta.get("process", {}).get("stages", {}).get("chunking", {})
        if chunking_stage.get("stage") != ProcessStage.CHUNKED:
            error_msg = f"文档必须先切片才能创建索引: {document_id}"
            logger.error(error_msg)
            await self.update_process_stage(
                user_id, document_id, "indexing", 
                {
                    "stage": ProcessStage.FAILED,
                    "success": False,
                    "error": error_msg,
                    "finished_at": time.time()
                }
            )
            return False
        
        # 更新状态为索引中
        await self.update_process_stage(
            user_id, document_id, "indexing", 
            {"stage": ProcessStage.INDEXING, "started_at": time.time()}
        )
        
        try:
            # 获取所有切片
            chunks_data = []
            chunks_texts = []
            
            async for chunk in self.iter_chunks(user_id, document_id):
                chunks_texts.append(chunk["content"])
                chunks_data.append({
                    "document_id": doc_meta["document_id"],
                    "chunk_index": chunk.get("chunk_index"),
                    "file_id": doc_meta["document_id"],
                    "user_id": user_id,
                    "original_name": doc_meta.get("original_name", ""),
                    "title": doc_meta.get("title", ""),
                    "source_type": doc_meta.get("source_type", ""),
                    "source_url": doc_meta.get("source_url", ""),
                    "type": doc_meta.get("type", ""),
                    "extension": doc_meta.get("extension", ""),
                    "created_at": doc_meta.get("created_at")
                })
            
            if not chunks_texts:
                error_msg = f"文档没有可索引的切片: {document_id}"
                logger.error(error_msg)
                await self.update_process_stage(
                    user_id, document_id, "indexing", 
                    {
                        "stage": ProcessStage.FAILED,
                        "success": False,
                        "error": error_msg,
                        "finished_at": time.time()
                    }
                )
                return False
            
            # 确保检索器存在
            if not self.retriever:
                error_msg = "没有配置检索器"
                logger.error(error_msg)
                await self.update_process_stage(
                    user_id, document_id, "indexing", 
                    {
                        "stage": ProcessStage.FAILED,
                        "success": False,
                        "error": error_msg,
                        "finished_at": time.time()
                    }
                )
                return False
            
            # 每个步骤单独try-except，确保更精确的错误处理
            try:
                # 先移除该 document_id 的旧向量，避免冗余
                coll = self.default_indexing_collection(user_id)
                await self.retriever.delete(collection_name=coll, user_id=user_id, document_id=document_id)
            except Exception as e:
                logger.warning(f"删除旧索引失败，继续添加新索引: {str(e)}")
            
            try:
                # 添加到向量索引
                collection_name = self.default_indexing_collection(user_id)
                result = await self.retriever.add(
                    texts=chunks_texts,
                    collection_name=collection_name,
                    user_id=user_id,
                    metadatas=chunks_data
                )
            except Exception as e:
                error_msg = f"添加向量索引失败: {str(e)}"
                logger.error(error_msg)
                await self.update_process_stage(
                    user_id, document_id, "indexing", 
                    {
                        "stage": ProcessStage.FAILED,
                        "success": False,
                        "error": error_msg,
                        "finished_at": time.time()
                    }
                )
                return False
            
            try:
                # 确保创建索引
                await self.retriever.ensure_index(collection_name)
            except Exception as e:
                logger.warning(f"确保索引操作失败，但数据已添加: {str(e)}")
            
            # 更新状态为索引完成
            now = time.time()
            await self.update_process_stage(
                user_id, document_id, "indexing", 
                {
                    "stage": ProcessStage.INDEXED,
                    "success": True,
                    "finished_at": now,
                    "details": {
                        "indexed_chunks": result.get("added", 0),
                        "total_chunks": len(chunks_texts)
                    }
                }
            )
            
            # 更新文档元数据
            await self.update_metadata(user_id, document_id, {
                "vector_index": {
                    "collection_name": collection_name,
                    "indexed_at": now,
                    "indexed_chunks": result.get("added", 0)
                },
                "process": {"current_stage": ProcessStage.INDEXED}
            })
            
            return True
            
        except Exception as e:
            error_msg = f"创建文档索引失败: {str(e)}"
            logger.error(error_msg)
            # 更新状态为失败
            await self.update_process_stage(
                user_id, document_id, "indexing", 
                {
                    "stage": ProcessStage.FAILED,
                    "success": False,
                    "error": error_msg,
                    "finished_at": time.time()
                }
            )
            return False
    
    async def search_documents(
        self,
        user_id: str,
        query: str,
        document_id: str = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """搜索文档内容"""
        
        # 调试日志：记录搜索参数
        logger.info(f"DocumentService.search_documents 被调用: 用户={user_id}, 文档ID={document_id}, 查询='{query[:50]}...'")
        logger.info(f"retriever存在: {self.retriever is not None}")
        
        # 确定集合名称
        collection_name = self.default_indexing_collection(user_id)
        logger.info(f"使用集合: {collection_name}")
        
        # 如果没有retriever，直接返回空结果
        if not self.retriever:
            logger.error("没有配置 retriever，无法执行搜索")
            return []
        
        try:
            # 使用实例属性中的检索器
            retr = self.retriever
            
            # 构建搜索过滤条件
            filter_str = None
            if document_id:
                filter_str = f"document_id = '{document_id}'"
            
            # 执行向量搜索
            results = await retr.query(
                query_texts=query,
                collection_name=collection_name,
                user_id=user_id,
                limit=limit,
                filter=filter_str
            )
            
            # 处理搜索结果
            if results and len(results) > 0:
                # 获取第一个查询的结果（如果只有一个查询文本）
                search_results = results[0].get("results", [])
                
                # 格式化返回结果
                formatted_results = []
                for result in search_results:
                    metadata = result.get("metadata", {})
                    formatted_result = {
                        "content": result.get("text", ""),
                        "score": result.get("score", 1.0),
                        "document_id": metadata.get("document_id", ""),
                        "chunk_index": metadata.get("chunk_index", 0),
                        "title": metadata.get("title", ""),
                        "original_name": metadata.get("original_name", "")
                    }
                    formatted_results.append(formatted_result)
                
                return formatted_results
            
            return []
            
        except Exception as e:
            logger.error(f"搜索文档失败: {str(e)}")
            return []

