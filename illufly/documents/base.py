import os
import shutil
import uuid
import time
import aiofiles
import logging
import mimetypes
import asyncio
import json

from enum import Enum
from typing import List, Dict, Any, Optional, AsyncGenerator, Literal
from pathlib import Path
from fastapi import UploadFile
from voidrail import ClientDealer

from ..llm.retriever.lancedb import LanceRetriever
from .machine import DocumentMachine

class DocumentStatus(str, Enum):
    """文档状态枚举"""
    ACTIVE = "active"      # 活跃状态，可用
    DELETED = "deleted"    # 已删除
    PROCESSING = "processing"  # 处理中（任何处理阶段）

class DocumentService:
    """文档管理服务
    
    基于约定的文件组织结构：
    - {user_id}/raw/{document_id} - 原始文件
    - {user_id}/md/{document_id}.md - Markdown文件
    - {user_id}/chunks/{document_id}/ - 切片目录
    - {user_id}/meta/{document_id}.json - 元数据


    元数据示例：
    {
        "document_id": "abc123",
        "original_name": "example.pdf",
        "size": 12345,
        "type": "pdf",
        "extension": ".pdf",
        "source_type": "local",
        "created_at": 1234567890,
        "updated_at": 1234567890,
        "status": "active",
        "state": "uploaded",
        "process_details": {
            "markdown": {
            "state": "not_started",
            "started_at": null,
            "finished_at": null,
            "success": false,
            "error": null
            },
            "chunking": {
            "state": "not_started",
            "started_at": null,
            "finished_at": null,
            "success": false,
            "error": null
            },
            "embedding": {
            "state": "not_started",
            "started_at": null,
            "finished_at": null,
            "success": false,
            "error": null
            },
            "qa_extraction": {
            "state": "not_applicable",
            "started_at": null,
            "finished_at": null,
            "success": false,
            "error": null
            }
        },
        "has_markdown": false,
        "has_chunks": false,
        "has_embeddings": false,
        "has_qa_pairs": false
    }

    """
    
    def __init__(
        self, 
        base_dir: str, 
        max_file_size: int = 50 * 1024 * 1024,  # 默认50MB 
        max_total_size_per_user: int = 200 * 1024 * 1024,  # 默认200MB
        allowed_extensions: List[str] = None,
        voidrail_client: ClientDealer = None,
        retriever: LanceRetriever = None,
        max_versions: int = 5,
        logger: logging.Logger = None
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

        self.logger = logger or logging.getLogger(__name__)

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
            self.logger.error(f"检查文档存在性失败: {user_id}/{document_id}, 错误: {e}")
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
        
        # 创建元数据 - 使用新的状态机状态
        now = time.time()
        
        # 初始化元数据
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
            "state": "uploaded",  # 状态机初始状态为uploaded
            "process_details": {
                "markdown": {
                    "state": "not_started",
                    "started_at": None,
                    "finished_at": None,
                    "success": False,
                    "error": None
                },
                "chunking": {
                    "state": "not_started",
                    "started_at": None,
                    "finished_at": None,
                    "success": False,
                    "error": None
                },
                "embedding": {
                    "state": "not_started",
                    "started_at": None,
                    "finished_at": None,
                    "success": False,
                    "error": None
                },
                "qa_extraction": {
                    "state": "not_applicable",
                    "started_at": None,
                    "finished_at": None,
                    "success": False,
                    "error": None
                }
            },
            "has_markdown": False,
            "has_chunks": False,
            "has_embeddings": False,
            "has_qa_pairs": False
        }
        
        # 添加额外元数据
        if metadata:
            for key in ["document_id", "created_at", "status", "state"]:
                if key in metadata:
                    del metadata[key]
            doc_meta.update(metadata)
        
        # 保存元数据
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
        
        # 创建元数据 - 使用状态机状态
        now = time.time()
        
        # 初始化元数据
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
            "state": "ready",  # 状态机初始状态
            "process_details": {
                "markdowning": {
                    "started_at": None,
                    "finished_at": None,
                    "success": False
                },
                "chunking": {
                    "started_at": None,
                    "finished_at": None,
                    "success": False
                },
                "embedding": {
                    "started_at": None,
                    "finished_at": None,
                    "success": False
                }
            },
            "has_markdown": False,
            "has_chunks": False,
            "has_embeddings": False
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
    
    async def get_document_machine(self, user_id: str, document_id: str) -> DocumentMachine:
        """获取文档状态机"""
        doc_meta = await self.get_document_meta(user_id, document_id)
        if not doc_meta:
            raise FileNotFoundError(f"文档不存在: {document_id}")
        
        # 创建状态机实例
        machine = DocumentMachine(self, user_id, document_id)
        
        # 激活初始状态 - 这一步是必需的
        await machine.activate_initial_state()
        
        # 获取当前元数据中的状态
        current_state = doc_meta.get("state", "uploaded")
        self.logger.debug(f"元数据中的状态: {current_state}")
        
        # 映射当前状态到状态机状态
        state_mapping = {
            # 来源状态
            "uploaded": machine.uploaded,
            "bookmarked": machine.bookmarked,
            "saved_chat": machine.saved_chat,
            
            # Markdown处理状态
            "markdowning": machine.markdowning,
            "markdowned": machine.markdowned,
            "markdown_failed": machine.markdown_failed,
            
            # 切片状态
            "chunking": machine.chunking,
            "chunked": machine.chunked,
            "chunk_failed": machine.chunk_failed,
            
            # QA处理状态
            "qa_extracting": machine.qa_extracting,
            "qa_extracted": machine.qa_extracted,
            "qa_extract_failed": machine.qa_extract_failed,
            
            # 向量化状态
            "embedding": machine.embedding,
            "embedded": machine.embedded,
            "embedding_failed": machine.embedding_failed
        }
        
        # 如果元数据状态有效，更新状态机状态
        if current_state in state_mapping:
            self.logger.info(f"设置状态机状态为 {current_state}")
            machine.current_state = state_mapping[current_state]
        
        return machine
    
    async def save_markdown(self, user_id: str, document_id: str, markdown_content: str = None) -> Dict[str, Any]:
        """保存文档的Markdown版本（使用状态机）"""
        try:
            # 检查文档是否存在
            if not await self.document_exists(user_id, document_id):
                raise FileNotFoundError(f"文档不存在: {document_id}")
            
            # 获取状态机并确保初始化
            machine = await self.get_document_machine(user_id, document_id)
            self.logger.info(f"Markdown处理开始，当前状态: {machine.current_state.id}")
            
            # 开始Markdown转换
            try:
                await machine.start_markdown()
            except Exception as e:
                self.logger.warning(f"开始Markdown处理出错: {e}, 尝试强制更新状态")
                await self.update_metadata(user_id, document_id, {"state": "markdowning"})
                # 重新获取状态机
                machine = await self.get_document_machine(user_id, document_id)
            
            # 获取文档元数据
            doc_meta = await self.get_document_meta(user_id, document_id)
            source_type = doc_meta.get("source_type", "local")
            
            # 获取markdown文件路径
            md_path = self.get_md_path(user_id, document_id)
            
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
            
            # 计算文档统计信息
            import re
            headers_count = len(re.findall(r'^#{1,6}\s+.+$', markdown_content, re.MULTILINE))
            paragraphs_count = len(re.split(r'\n\s*\n', markdown_content))
            
            # 完成Markdown转换
            await machine.complete_markdown()
            
            return await self.get_document_meta(user_id, document_id)
            
        except Exception as e:
            try:
                # 如果发生错误，将状态机设为失败
                machine = await self.get_document_machine(user_id, document_id)
                await machine.fail_markdown(error=str(e))
            except Exception as inner_e:
                self.logger.error(f"状态机更新失败: {inner_e}")
            
            self.logger.error(f"Markdown转换失败: {e}")
            raise
            
        finally:
            return await self.get_document_meta(user_id, document_id)

    async def get_markdown(self, user_id: str, document_id: str) -> str:
        """获取文档的Markdown内容"""
        md_path = self.get_md_path(user_id, document_id)
        
        if not md_path.exists():
            return ""
        
        try:
            async with aiofiles.open(md_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                return content
        except Exception as e:
            self.logger.error(f"读取Markdown内容失败: {e}")
            return ""    

    async def save_chunks(self, user_id: str, document_id: str, chunks: List[Dict[str, Any]] = None) -> bool:
        """保存文档切片（使用状态机）"""
        try:
            # 检查文档是否存在
            if not await self.document_exists(user_id, document_id):
                raise FileNotFoundError(f"文档不存在: {document_id}")
            
            # 获取文档元数据并确认状态
            doc_meta = await self.get_document_meta(user_id, document_id)
            current_state = doc_meta.get("state", "ready")
            self.logger.debug(f"开始切片前的文档状态: {current_state}")
            
            # 如果不是markdowned状态，处理特殊情况
            if current_state != "markdowned":
                self.logger.warning(f"文档状态 ({current_state}) 不是 markdowned，尝试处理")
                
                # 如果是ready状态并且已有markdown，强制更新状态
                if current_state == "ready" and doc_meta.get("has_markdown"):
                    self.logger.info("文档有Markdown但状态是ready，强制更新状态为markdowned")
                    await self.update_metadata(user_id, document_id, {"state": "markdowned"})
                    current_state = "markdowned"
                
                # 如果仍然不是markdowned，尝试创建markdown
                if current_state != "markdowned":
                    self.logger.info("尝试先创建Markdown")
                    await self.save_markdown(user_id, document_id)
                    doc_meta = await self.get_document_meta(user_id, document_id)
                    current_state = doc_meta.get("state")
            
            # 重新获取状态机，确保状态同步
            machine = await self.get_document_machine(user_id, document_id)
            self.logger.debug(f"当前状态机状态: {machine.current_state.id}, 元数据状态: {current_state}")
            
            # 开始切片
            try:
                await machine.start_chunking()
            except Exception as e:
                self.logger.error(f"开始切片失败: {e}")
                if "Can't start_chunking" in str(e):
                    # 特殊处理：如果metadata显示markdowned但状态机不同步
                    await self.update_metadata(user_id, document_id, {"state": "chunking"})
                    machine = await self.get_document_machine(user_id, document_id)
                else:
                    return False
            
            # 此处插入切片处理逻辑...
            # 假设chunks参数已提供有效切片
            if chunks:
                # 保存切片文件
                chunks_dir = self.get_chunks_dir(user_id, document_id)
                # ...切片保存逻辑...
                
                # 保存切片元数据
                await self.update_metadata(
                    user_id, document_id,
                    {"chunks": chunks}
                )
            
            # 完成切片
            chunks_stats = {
                "count": len(chunks) if chunks else 0,
                "avg_length": sum(len(chunk.get("content", "")) for chunk in chunks) // max(len(chunks), 1) if chunks else 0
            }
            
            try:
                await machine.complete_chunking(
                    chunks_count=chunks_stats["count"],
                    avg_length=chunks_stats["avg_length"]
                )
            except Exception as e:
                self.logger.error(f"完成切片失败: {e}")
                await self.update_metadata(
                    user_id, document_id,
                    {
                        "state": "chunked",
                        "has_chunks": True
                    }
                )
            
            return True
            
        except Exception as e:
            self.logger.error(f"保存切片过程中发生错误: {e}")
            return False
    
    async def create_document_index(
        self, 
        user_id: str, 
        document_id: str, 
        source_type: Literal["chunks", "qa_pairs"] = None
    ) -> bool:
        """创建文档索引（使用状态机）"""
        try:
            # 检查文档是否存在
            if not await self.document_exists(user_id, document_id):
                raise FileNotFoundError(f"文档不存在: {document_id}")
            
            # 获取状态机和元数据
            machine = await self.get_document_machine(user_id, document_id)
            doc_meta = await self.get_document_meta(user_id, document_id)
            
            # 确定索引来源类型
            if not source_type:
                if doc_meta.get("source_type") == "chat" and doc_meta.get("has_qa_pairs", False):
                    source_type = "qa_pairs"
                elif doc_meta.get("has_chunks", False):
                    source_type = "chunks"
                else:
                    raise ValueError("无法确定索引来源类型，文档没有切片或QA对")
            
            # 开始向量化
            if source_type == "chunks" and machine.current_state.id == "chunked":
                await machine.start_embedding_from_chunks()
            elif source_type == "qa_pairs" and machine.current_state.id == "qa_extracted":
                await machine.start_embedding_from_qa()
            else:
                raise ValueError(f"文档状态({machine.current_state.id})不支持向量化，或索引类型({source_type})不匹配")
            
            # 向量化处理逻辑
            # ...
            
            # 成功完成向量化
            await machine.complete_embedding(indexed_chunks=result.get("added", 0))
            
            return True
            
        except Exception as e:
            try:
                # 失败处理
                machine = await self.get_document_machine(user_id, document_id)
                await machine.fail_embedding(error=str(e))
            except Exception as inner_e:
                self.logger.error(f"状态机更新失败: {inner_e}")
                
            self.logger.error(f"向量化处理失败: {e}")
            return False
    
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
            self.logger.warning(f"尝试删除不存在的文档: {document_id}")
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
            self.logger.error(f"删除向量索引失败: {e}")

        success = True
        # 1. 删除原始文件
        raw_path = self.get_raw_path(user_id, document_id)
        if raw_path.exists():
            try:
                os.remove(raw_path)
            except Exception as e:
                self.logger.error(f"删除原始文件失败: {raw_path}, 错误: {e}")
                success = False
        
        # 2. 删除Markdown文件
        md_path = self.get_md_path(user_id, document_id)
        if md_path.exists():
            try:
                os.remove(md_path)
            except Exception as e:
                self.logger.error(f"删除Markdown文件失败: {md_path}, 错误: {e}")
                success = False
        
        # 3. 删除切片目录
        chunks_dir = self.get_chunks_dir(user_id, document_id)
        if chunks_dir.exists():
            try:
                shutil.rmtree(chunks_dir)
            except Exception as e:
                self.logger.error(f"删除切片目录失败: {chunks_dir}, 错误: {e}")
                success = False
        
        # 4. 最后才删除元数据
        meta_path = self.get_meta_path(user_id, document_id)
        if meta_path.exists():
            try:
                os.remove(meta_path)
            except Exception as e:
                self.logger.error(f"删除元数据失败: {meta_path}, 错误: {e}")
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
                self.logger.error(f"读取文档元数据失败: {meta_path}, 错误: {e}")
        
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
            self.logger.error(f"读取文档元数据失败: {meta_path}, 错误: {e}")
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
            self.logger.error(f"更新元数据失败: {str(e)}")
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

    async def search_documents(
        self,
        user_id: str,
        query: str,
        document_id: str = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """搜索文档内容"""
        
        # 调试日志：记录搜索参数
        self.logger.info(f"DocumentService.search_documents 被调用: 用户={user_id}, 文档ID={document_id}, 查询='{query[:50]}...'")
        self.logger.info(f"retriever存在: {self.retriever is not None}")
        
        # 确定集合名称
        collection_name = self.default_indexing_collection(user_id)
        self.logger.info(f"使用集合: {collection_name}")
        
        # 如果没有retriever，直接返回空结果
        if not self.retriever:
            self.logger.error("没有配置 retriever，无法执行搜索")
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
                        "distance": result.get("distance", 1.0),
                        "document_id": metadata.get("document_id", ""),
                        "chunk_index": metadata.get("chunk_index", 0),
                        "title": metadata.get("title", ""),
                        "original_name": metadata.get("original_name", "")
                    }
                    formatted_results.append(formatted_result)
                
                return formatted_results
            
            return []
            
        except Exception as e:
            self.logger.error(f"搜索文档失败: {str(e)}")
            return []

    async def on_enter_ready(self):
        """进入就绪状态"""
        self.logger.info(f"文档 {self.document_id} 重置为就绪状态")
        await self.service.update_metadata(
            self.user_id, self.document_id,
            {
                "state": "ready",
                "process_details": {
                    "markdowning": {
                        "stage": None,
                        "started_at": None,
                        "finished_at": None,
                        "success": False,
                        "error": None
                    },
                    "chunking": {
                        "stage": None,
                        "started_at": None,
                        "finished_at": None,
                        "success": False,
                        "error": None
                    },
                    "embedding": {
                        "stage": None,
                        "finished_at": None, 
                        "success": False,
                        "error": None
                    }
                },
                "has_markdown": False,
                "has_chunks": False,
                "has_embeddings": False
            }
        )

    async def create_bookmark_document(
        self,
        user_id: str,
        url: str,
        title: str,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """创建网络书签文档"""
        document_id = self.generate_document_id(title + ".url")
        meta_path = self.get_meta_path(user_id, document_id)
        
        # 创建元数据
        now = time.time()
        
        # 初始化元数据
        doc_meta = {
            "document_id": document_id,
            "original_name": title,
            "source_type": "web",
            "source_url": url,
            "created_at": now,
            "updated_at": now,
            "status": DocumentStatus.ACTIVE,
            "state": "bookmarked",  # 状态机初始状态为bookmarked
            "process_details": {
                "markdown": {
                    "state": "not_started",
                    "started_at": None,
                    "finished_at": None,
                    "success": False,
                    "error": None
                },
                "chunking": {
                    "state": "not_started",
                    "started_at": None,
                    "finished_at": None,
                    "success": False,
                    "error": None
                },
                "embedding": {
                    "state": "not_started", 
                    "started_at": None,
                    "finished_at": None,
                    "success": False,
                    "error": None
                },
                "qa_extraction": {
                    "state": "not_applicable",
                    "started_at": None,
                    "finished_at": None,
                    "success": False,
                    "error": None
                }
            },
            "has_markdown": False,
            "has_chunks": False,
            "has_embeddings": False,
            "has_qa_pairs": False
        }
        
        # 添加额外元数据
        if metadata:
            for key in ["document_id", "created_at", "status", "state"]:
                if key in metadata:
                    del metadata[key]
            doc_meta.update(metadata)
        
        # 保存元数据
        async with aiofiles.open(meta_path, 'w') as meta_file:
            await meta_file.write(json.dumps(doc_meta, ensure_ascii=False))
        
        return doc_meta

    async def create_chat_document(
        self,
        user_id: str,
        chat_id: str,
        title: str,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """创建对话记录文档"""
        document_id = self.generate_document_id(title + ".chat")
        meta_path = self.get_meta_path(user_id, document_id)
        
        # 创建元数据
        now = time.time()
        
        # 初始化元数据
        doc_meta = {
            "document_id": document_id,
            "original_name": title,
            "source_type": "chat",
            "chat_id": chat_id,
            "created_at": now,
            "updated_at": now,
            "status": DocumentStatus.ACTIVE,
            "state": "saved_chat",  # 状态机初始状态为saved_chat
            "process_details": {
                "markdown": {
                    "state": "not_applicable",
                    "started_at": None,
                    "finished_at": None,
                    "success": False,
                    "error": None
                },
                "chunking": {
                    "state": "not_applicable",
                    "started_at": None,
                    "finished_at": None,
                    "success": False,
                    "error": None
                },
                "embedding": {
                    "state": "not_started",
                    "started_at": None,
                    "finished_at": None,
                    "success": False,
                    "error": None
                },
                "qa_extraction": {
                    "state": "not_started",
                    "started_at": None,
                    "finished_at": None,
                    "success": False,
                    "error": None
                }
            },
            "has_markdown": False,
            "has_chunks": False,
            "has_embeddings": False,
            "has_qa_pairs": False
        }
        
        # 添加额外元数据
        if metadata:
            for key in ["document_id", "created_at", "status", "state"]:
                if key in metadata:
                    del metadata[key]
            doc_meta.update(metadata)
        
        # 保存元数据
        async with aiofiles.open(meta_path, 'w') as meta_file:
            await meta_file.write(json.dumps(doc_meta, ensure_ascii=False))
        
        return doc_meta

    async def save_qa_pairs(self, user_id: str, document_id: str, qa_pairs: List[Dict[str, str]]) -> bool:
        """保存QA对（使用状态机）"""
        try:
            # 检查文档是否存在
            if not await self.document_exists(user_id, document_id):
                raise FileNotFoundError(f"文档不存在: {document_id}")
            
            # 获取状态机和元数据
            machine = await self.get_document_machine(user_id, document_id)
            doc_meta = await self.get_document_meta(user_id, document_id)
            
            # 检查文档来源是否为对话
            if doc_meta.get("source_type") != "chat":
                raise ValueError("只有对话记录文档可以提取QA对")
            
            # 只有在需要时才启动QA提取（状态不是qa_extracting）
            if machine.current_state.id != "qa_extracting":
                await machine.start_qa_extraction()
            
            # 保存QA对到文件
            qa_dir = self.get_user_dir(user_id, "qa_pairs") / document_id
            qa_dir.mkdir(parents=True, exist_ok=True)
            qa_path = qa_dir / "qa_pairs.json"
            
            async with aiofiles.open(qa_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(qa_pairs, ensure_ascii=False))
            
            # 更新元数据
            await self.update_metadata(
                user_id, document_id,
                {
                    "qa_pairs_count": len(qa_pairs)
                }
            )
            
            # 完成QA提取
            await machine.complete_qa_extraction(qa_pairs_count=len(qa_pairs))
            
            return True
            
        except Exception as e:
            self.logger.error(f"保存QA对失败: {e}")
            # 更新状态为失败
            try:
                machine = await self.get_document_machine(user_id, document_id)
                await machine.fail_qa_extraction(error=str(e))
            except Exception:
                pass
            return False

    async def on_enter_qa_extracted(self, qa_pairs_count=0):
        """QA提取完成"""
        self.logger.info(f"文档 {self.document_id} QA提取完成，共{qa_pairs_count}个问答对")
        now = time.time()
        await self.service.update_metadata(
            self.user_id, self.document_id,
            {
                "state": "qa_extracted",
                "process_details": {
                    "qa_extraction": {
                        "stage": "completed",
                        "finished_at": now,
                        "success": True,
                        "details": {
                            "qa_pairs_count": qa_pairs_count
                        }
                    }
                },
                "has_qa_pairs": True
            }
        )

