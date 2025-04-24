from typing import List, Dict, Any, Optional, AsyncGenerator
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

logger = logging.getLogger(__name__)

class DocumentStatus:
    """文档状态枚举"""
    ACTIVE = "active"              # 活跃状态
    DELETED = "deleted"            # 已删除
    PROCESSING = "processing"      # 处理中

class ProcessStage:
    """处理阶段枚举"""
    NONE = "none"                  # 未处理
    QUEUED = "queued"              # 队列中
    CONVERTING = "converting"      # 转换中
    CONVERTED = "converted"        # 已转换
    CHUNKING = "chunking"          # 切片中
    CHUNKED = "chunked"            # 已切片
    INDEXING = "indexing"          # 索引中
    INDEXED = "indexed"            # 已索引
    FAILED = "failed"              # 处理失败

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
        voidrail_client: ClientDealer = None
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
        
        # 创建元数据
        now = time.time()
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
            "process": {
                "current_stage": ProcessStage.NONE,
                "stages": {
                    "conversion": {
                        "stage": ProcessStage.NONE,
                        "success": False,
                        "started_at": None,
                        "finished_at": None
                    },
                    "chunking": {
                        "stage": ProcessStage.NONE,
                        "success": False,
                        "started_at": None,
                        "finished_at": None
                    },
                    "indexing": {
                        "stage": ProcessStage.NONE,
                        "success": False,
                        "started_at": None,
                        "finished_at": None
                    }
                }
            }
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
        
        # 创建元数据
        now = time.time()
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
            "process": {
                "current_stage": ProcessStage.NONE,
                "stages": {
                    "conversion": {
                        "stage": ProcessStage.NONE,
                        "success": False,
                        "started_at": None,
                        "finished_at": None
                    },
                    "chunking": {
                        "stage": ProcessStage.NONE,
                        "success": False,
                        "started_at": None,
                        "finished_at": None
                    },
                    "indexing": {
                        "stage": ProcessStage.NONE,
                        "success": False,
                        "started_at": None,
                        "finished_at": None
                    }
                }
            }
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
            
            # 获取markdown文件路径
            raw_path = self.get_raw_path(user_id, document_id)
            md_path = self.get_md_path(user_id, document_id)
            
            await self.update_process_stage(
                user_id, document_id, "conversion", 
                {"stage": ProcessStage.CONVERTING, "started_at": time.time()}
            )

            # 转换markdown内容
            if markdown_content is None:
                markdown_content = ""  # 初始化为空字符串
                resp = self.voidrail_client.stream(
                    method="SimpleDocling.local_convert",
                    timeout=600,
                    from_path=str(os.path.abspath(raw_path))  # 将Path对象转为字符串
                )
                async for chunk in resp:
                    markdown_content += chunk

                # 更新当前阶段
                await self.update_metadata(user_id, document_id, {
                    "process": {"current_stage": ProcessStage.CONVERTED}
                })

            # 保存markdown文件
            async with aiofiles.open(md_path, 'w', encoding='utf-8') as f:
                await f.write(markdown_content)
            
            # 完成处理并更新状态
            now = time.time()
            await self.update_process_stage(
                user_id, document_id, "conversion", 
                {
                    "stage": ProcessStage.CONVERTED,
                    "success": True,
                    "finished_at": now,
                    "details": {
                        "content_length": len(markdown_content)
                    }
                }
            )

        except Exception as e:
            logger.error(f"转换markdown内容失败: {e}")
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
        chunks: List[Dict[str, Any]]
    ) -> bool:
        """保存文档的切片"""
        try:
            # 检查文档是否存在
            if not await self.document_exists(user_id, document_id):
                raise FileNotFoundError(f"文档不存在: {document_id}")
            
            # 创建切片目录
            chunks_dir = self.get_chunks_dir(user_id, document_id)
            
            # 开始处理并更新状态
            await self.update_process_stage(
                user_id, document_id, "chunking", 
                {"stage": ProcessStage.CHUNKING, "started_at": time.time()}
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
                    
                chunks_meta.append(chunk_meta)
            
            # 完成处理并更新状态
            now = time.time()
            await self.update_metadata(user_id, document_id, {
                "chunks": chunks_meta,
                "chunks_count": len(chunks),
                "process": {
                    "current_stage": ProcessStage.CHUNKED,
                    "stages": {
                        "chunking": {
                            "stage": ProcessStage.CHUNKED,
                            "success": True,
                            "finished_at": now,
                            "details": {
                                "chunks_count": len(chunks)
                            }
                        }
                    }
                }
            })
            
            return True
        
        except Exception as e:
            logger.error(f"保存切片失败: {str(e)}")
            
            # 更新状态为失败
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
            
            # 读取切片
            for chunk_meta in doc_meta.get("chunks", []):
                try:
                    chunk_path = Path(chunk_meta["path"])
                    if not chunk_path.exists():
                        continue
                        
                    async with aiofiles.open(chunk_path, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        
                        yield {
                            "document_id": document_id,
                            "chunk_index": chunk_meta["index"],
                            "content": content,
                            "metadata": chunk_meta.get("metadata", {})
                        }
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
        stage_name: str,
        stage_data: Dict[str, Any]
    ) -> bool:
        """更新文档处理阶段状态"""
        metadata = {
            "process": {
                "stages": {
                    stage_name: stage_data
                }
            }
        }
        
        if "stage" in stage_data:
            metadata["process"]["current_stage"] = stage_data["stage"]
            
        return await self.update_metadata(user_id, document_id, metadata)
    
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

