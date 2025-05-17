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
from typing import List, Dict, Any, Optional, AsyncGenerator, Literal, Tuple, Union
from pathlib import Path
from fastapi import UploadFile

from ..llm.retriever.lancedb import LanceRetriever
from .processor import DocumentProcessor
from .meta import DocumentMetaManager

# 定义错误类型枚举
class ErrorType(str, Enum):
    VALIDATION_ERROR = "validation_error"  # 验证错误（如状态检查失败）
    FILE_ERROR = "file_error"  # 文件操作错误
    DATABASE_ERROR = "database_error"  # 数据库错误
    RESOURCE_ERROR = "resource_error"  # 资源（向量存储等）错误
    UNKNOWN_ERROR = "unknown_error"  # 未知错误

# 定义结果类型，使用泛型
class Result:
    """统一的结果类型，包含成功标志、数据和错误信息"""
    
    def __init__(
        self, 
        success: bool, 
        data: Any = None, 
        error_type: ErrorType = None,
        error_message: str = None,
        error_detail: Dict[str, Any] = None
    ):
        self.success = success
        self.data = data
        self.error_type = error_type
        self.error_message = error_message
        self.error_detail = error_detail or {}
    
    @classmethod
    def ok(cls, data: Any = None) -> 'Result':
        """创建成功结果"""
        return cls(success=True, data=data)
    
    @classmethod
    def fail(cls,
             error_type: ErrorType, 
             error_message: str, 
             error_detail: Dict[str, Any] = None) -> 'Result':
        """创建失败结果"""
        return cls(
            success=False, 
            error_type=error_type, 
            error_message=error_message,
            error_detail=error_detail
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，用于API响应"""
        if self.success:
            return {
                "success": True,
                "data": self.data
            }
        else:
            return {
                "success": False,
                "error": {
                    "type": self.error_type,
                    "message": self.error_message,
                    "detail": self.error_detail
                }
            }

class DocumentService:
    """简化的文档服务 - 协调文档处理和元数据管理的操作"""
    
    def __init__(
        self, 
        base_dir: str, 
        max_file_size: int = 50 * 1024 * 1024,
        max_total_size_per_user: int = 200 * 1024 * 1024,
        allowed_extensions: List[str] = None,
        embedding_config: Dict[str, Any] = {},
        logger = None
    ):
        self.base_dir = Path(base_dir)
        self.max_file_size = max_file_size
        self.max_total_size_per_user = max_total_size_per_user
        
        # 创建核心组件
        self.meta_manager = DocumentMetaManager(
            meta_dir=str(self.base_dir / "meta"),
            docs_dir=str(self.base_dir / "docs")
        )
        
        # 创建处理器，委托其初始化向量检索器
        self.processor = DocumentProcessor(
            docs_dir=str(self.base_dir / "docs"),
            meta_manager=self.meta_manager,
            max_file_size=max_file_size,
            allowed_extensions=allowed_extensions,
            vector_db_path=str(self.base_dir / "vector_db"),
            embedding_config=embedding_config,
            logger=logger
        )

        self.logger = logger or logging.getLogger(__name__)
    
    async def create_document(self, user_id: str, doc_info: Dict[str, Any], 
                            topic_path: str = None, metadata: Dict[str, Any] = None) -> Result:
        """创建文档元数据 - 业务流程起点"""
        try:
            if not user_id or not doc_info or "document_id" not in doc_info:
                return Result.fail(
                    ErrorType.VALIDATION_ERROR,
                    "无效的参数: 必须提供user_id和包含document_id的doc_info",
                    {"provided": {"user_id": bool(user_id), "doc_info": bool(doc_info)}}
                )
            
            document_id = doc_info["document_id"]
            
            # 检查文档是否已存在
            existing_doc = await self.meta_manager.get_metadata(user_id, document_id)
            if existing_doc:
                return Result.fail(
                    ErrorType.VALIDATION_ERROR,
                    f"文档已存在: {document_id}",
                    {"document_id": document_id}
                )
            
            # 创建元数据
            now = int(time.time())
            meta = {
                **doc_info,
                "created_at": now,
                "updated_at": now,
                "topic_path": topic_path,
                "processed": False  # 初始状态为未处理
            }
            
            # 合并用户元数据
            if metadata:
                # 过滤保留字段
                for key in ["document_id", "created_at", "processed"]:
                    if key in metadata:
                        del metadata[key]
                meta.update(metadata)
            
            # 保存元数据
            doc_meta = await self.meta_manager.create_document(
                user_id, document_id, topic_path, meta
            )
            
            return Result.ok(doc_meta)
        except Exception as e:
            error_type, error_message, error_detail = self._classify_exception(e)
            self.logger.error(f"创建文档失败: {error_message}", exc_info=True)
            error_detail["user_id"] = user_id
            error_detail["document_id"] = doc_info.get("document_id") if doc_info else None
            return Result.fail(error_type, error_message, error_detail)
        
    async def upload_document(self, user_id: str, file: UploadFile, topic_path: str = None, 
                            metadata: Dict[str, Any] = None, auto_process: bool = False) -> Result:
        """上传文档并可选择自动处理"""
        try:
            # 1. 处理文件上传
            if not file or not file.filename:
                return Result.fail(
                    ErrorType.VALIDATION_ERROR,
                    "无效的文件: 必须提供有效的文件",
                    {"file_provided": bool(file)}
                )
                
            file_info_result = None
            try:
                file_info = await self.processor.save_and_get_file_info(
                    user_id, file, max_total_size=self.max_total_size_per_user
                )
                file_info_result = file_info
            except ValueError as ve:
                return Result.fail(
                    ErrorType.VALIDATION_ERROR,
                    str(ve),
                    {"user_id": user_id, "filename": file.filename}
                )
            except Exception as e:
                error_type, error_message, error_detail = self._classify_exception(e)
                error_detail["user_id"] = user_id
                error_detail["filename"] = file.filename
                return Result.fail(error_type, error_message, error_detail)
            
            # 2. 创建文档元数据
            doc_result = await self.create_document(user_id, file_info, topic_path, metadata)
            if not doc_result.success:
                # 如果创建元数据失败，但文件已上传，尝试清理文件
                if file_info_result:
                    try:
                        document_id = file_info_result.get("document_id")
                        if document_id:
                            await self.processor.remove_document_files(user_id, document_id)
                    except Exception as cleanup_e:
                        self.logger.error(f"清理已上传文件失败: {cleanup_e}", exc_info=True)
                
                return doc_result
            
            # 3. 如果需要自动处理，立即处理文档
            document_id = file_info["document_id"]
            if auto_process:
                process_result = await self.process_document(user_id, document_id)
                if not process_result.success:
                    self.logger.warning(f"文档自动处理失败: {process_result.error_message}")
                    # 更新元数据以记录处理失败
                    await self.meta_manager.update_metadata(
                        user_id, document_id, 
                        {
                            "processed": False,
                            "process_error": process_result.error_message
                        }
                    )
                    
                # 始终返回文档信息，即使处理失败
                doc_meta = await self.meta_manager.get_metadata(user_id, document_id)
                return Result.ok(doc_meta)
            
            return doc_result
        except Exception as e:
            error_type, error_message, error_detail = self._classify_exception(e)
            self.logger.error(f"上传文档失败: {error_message}", exc_info=True)
            error_detail["user_id"] = user_id
            return Result.fail(error_type, error_message, error_detail)
    
    async def create_bookmark(self, user_id: str, url: str, filename: str, 
                            topic_path: str = None, metadata: Dict[str, Any] = None,
                            auto_process: bool = False) -> Result:
        """创建网络书签文档，可选择自动处理"""
        try:
            # 1. 注册远程文档
            doc_info = await self.processor.register_remote_doc_info(user_id, url, filename)
            
            # 2. 创建文档元数据
            doc_result = await self.create_document(user_id, doc_info, topic_path, metadata)
            if not doc_result.success:
                return doc_result
            
            # 3. 如果需要自动处理，立即处理文档
            document_id = doc_info["document_id"]
            if auto_process:
                process_result = await self.process_document(user_id, document_id)
                if not process_result.success:
                    self.logger.warning(f"书签自动处理失败: {process_result.error_message}")
                    # 更新元数据以记录处理失败
                    await self.meta_manager.update_metadata(
                        user_id, document_id, 
                        {
                            "processed": False,
                            "process_error": process_result.error_message
                        }
                    )
                
                # 始终返回文档信息，即使处理失败
                doc_meta = await self.meta_manager.get_metadata(user_id, document_id)
                return Result.ok(doc_meta)
                
            return doc_result
        except Exception as e:
            error_type, error_message, error_detail = self._classify_exception(e)
            self.logger.error(f"创建书签失败: {error_message}", exc_info=True)
            error_detail["user_id"] = user_id
            error_detail["url"] = url
            return Result.fail(error_type, error_message, error_detail)
    
    async def process_document(self, user_id: str, document_id: str) -> Result:
        """一体化处理文档（转换、切片、嵌入）"""
        try:
            # 检查文档是否存在
            doc_meta = await self.meta_manager.get_metadata(user_id, document_id)
            if not doc_meta:
                return Result.fail(
                    ErrorType.RESOURCE_ERROR,
                    f"找不到文档: {document_id}",
                    {"user_id": user_id, "document_id": document_id}
                )
                
            # 如果文档已处理成功，直接返回
            if doc_meta.get("processed", False):
                return Result.ok({
                    "document_id": document_id,
                    "already_processed": True,
                    "message": "文档已处理，无需重复处理"
                })
            
            # 委托处理器执行一体化处理
            result = await self.processor.process_document_complete(user_id, document_id)
            
            return Result.ok(result)
        except Exception as e:
            error_type, error_message, error_detail = self._classify_exception(e)
            self.logger.error(f"处理文档失败: {error_message}", exc_info=True)
            error_detail["user_id"] = user_id
            error_detail["document_id"] = document_id
            return Result.fail(error_type, error_message, error_detail)
    
    async def delete_document(self, user_id: str, document_id: str) -> Result:
        """删除文档 - 协调资源清理"""
        try:
            # 检查文档是否存在
            doc_meta = await self.meta_manager.get_metadata(user_id, document_id)
            if not doc_meta:
                return Result.fail(
                    ErrorType.RESOURCE_ERROR,
                    f"找不到文档: {document_id}",
                    {"user_id": user_id, "document_id": document_id}
                )
                
            # 收集所有操作中的错误
            errors = []
            
            # 1. 从向量存储中删除
            try:
                # 删除内容切片向量
                await self.processor.remove_vector_embeddings(user_id, document_id)
                
                # 删除摘要向量
                await self.processor.remove_summary_vector(user_id, document_id)
            except Exception as ve:
                errors.append(f"从向量存储中删除失败: {str(ve)}")
            
            # 2. 删除文件资源
            try:
                await self.processor.remove_document_files(user_id, document_id)
            except Exception as fe:
                errors.append(f"删除文件资源失败: {str(fe)}")
            
            # 3. 删除元数据
            try:
                success = await self.meta_manager.delete_document(user_id, document_id)
                if not success:
                    errors.append("删除元数据失败")
            except Exception as me:
                errors.append(f"删除元数据异常: {str(me)}")
            
            # 如果有错误，返回部分成功
            if errors:
                return Result.fail(
                    ErrorType.RESOURCE_ERROR,
                    "文档删除部分失败",
                    {"user_id": user_id, "document_id": document_id, "errors": errors}
                )
            
            return Result.ok({"deleted": True, "document_id": document_id})
        except Exception as e:
            error_type, error_message, error_detail = self._classify_exception(e)
            self.logger.error(f"删除文档失败: {error_message}", exc_info=True)
            error_detail["user_id"] = user_id
            error_detail["document_id"] = document_id
            return Result.fail(error_type, error_message, error_detail)
    
    async def search_chunks(self, user_id: str, query: str, document_id: str = None, limit: int = 10) -> Result:
        """搜索文档内容 - 委托给处理器，并处理异常"""
        try:
            result = await self.processor.search_chunks(
                user_id, query, document_id, limit
            )
            
            return Result.ok(result)
        except Exception as e:
            error_type, error_message, error_detail = self._classify_exception(e)
            self.logger.error(f"搜索文档失败: {error_message}", exc_info=True)
            error_detail["user_id"] = user_id
            error_detail["query"] = query
            return Result.fail(error_type, error_message, error_detail)
    
    async def get_document(self, user_id: str, document_id: str) -> Optional[Dict[str, Any]]:
        """获取文档元数据"""
        return await self.meta_manager.get_metadata(user_id, document_id)
    
    async def list_documents(self, user_id: str, topic_path: str = None) -> List[Dict[str, Any]]:
        """列出用户的所有文档"""
        # 使用元数据管理器获取文档列表
        return await self.meta_manager.list_documents(user_id, topic_path)
    
    async def list_processed_documents(self, user_id: str, processed: bool = True) -> List[Dict[str, Any]]:
        """列出已处理或未处理的文档"""
        return await self.meta_manager.find_processed_documents(user_id, processed)

    async def update_document_metadata(
        self, 
        user_id: str, 
        document_id: str, 
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        summary: Optional[str] = None,
        is_public: Optional[bool] = None,
        allowed_roles: Optional[List[str]] = None,
        topic_path: Optional[str] = None,
        metadata: Dict[str, Any] = None
    ) -> Result:
        """更新文档元数据"""
        try:
            # 1. 检查文档是否存在
            doc_meta = await self.meta_manager.get_metadata(user_id, document_id)
            if not doc_meta:
                return Result.fail(
                    ErrorType.RESOURCE_ERROR,
                    f"找不到文档: {document_id}",
                    {"user_id": user_id, "document_id": document_id}
                )
            
            # 2. 构建更新数据，只包含非None的字段
            update_data = {}
            
            # 添加显式参数
            if title is not None:
                update_data["title"] = title
            if description is not None:
                update_data["description"] = description
            if tags is not None:
                update_data["tags"] = tags
            if summary is not None:
                update_data["summary"] = summary
            if is_public is not None:
                update_data["is_public"] = is_public
            if allowed_roles is not None:
                update_data["allowed_roles"] = allowed_roles
            if topic_path is not None:
                update_data["topic_path"] = topic_path
            
            # 合并其他元数据
            if metadata:
                # 过滤已经作为显式参数的字段
                filtered_metadata = {k: v for k, v in metadata.items() 
                                    if k not in ["title", "description", "tags", "summary", 
                                                "is_public", "allowed_roles", "topic_path"]}
                if filtered_metadata:
                    # 如果元数据字段已存在，则合并而不是覆盖
                    existing_metadata = doc_meta.get("metadata", {})
                    update_data["metadata"] = {**existing_metadata, **filtered_metadata}
            
            # 3. 如果没有需要更新的字段，直接返回当前元数据
            if not update_data:
                return Result.ok(doc_meta)
            
            # 4. 更新元数据
            updated_meta = await self.meta_manager.update_metadata(
                user_id, document_id, update_data
            )
            
            if not updated_meta:
                return Result.fail(
                    ErrorType.DATABASE_ERROR,
                    "更新元数据失败",
                    {"user_id": user_id, "document_id": document_id}
                )
            
            # 5. 如果更新了摘要，则保存摘要向量
            if summary is not None:
                try:
                    # 委托给处理器处理向量存储
                    vector_result = await self.processor.update_document_summary_vector(
                        user_id=user_id,
                        document_id=document_id,
                        summary=summary,
                        doc_meta=updated_meta
                    )
                    
                    if not vector_result.get("success", False):
                        self.logger.warning(f"摘要向量更新失败: {vector_result.get('error', '未知错误')}")
                except Exception as ve:
                    # 向量存储失败不影响元数据更新结果
                    self.logger.error(f"保存摘要向量失败: {ve}", exc_info=True)
            
            # 6. 如果修改了topic_path，需要执行物理目录移动
            if topic_path is not None and topic_path != doc_meta.get("topic_path"):
                try:
                    move_result = await self.move_document_to_topic(user_id, document_id, topic_path)
                    if not move_result.success:
                        self.logger.warning(f"移动文档目录失败，但元数据已更新: {move_result.error_message}")
                except Exception as me:
                    self.logger.error(f"移动文档目录失败: {me}", exc_info=True)
            
            return Result.ok(updated_meta)
        except Exception as e:
            error_type, error_message, error_detail = self._classify_exception(e)
            self.logger.error(f"更新文档元数据失败: {error_message}", exc_info=True)
            error_detail["user_id"] = user_id
            error_detail["document_id"] = document_id
            return Result.fail(error_type, error_message, error_detail)

    async def move_document_to_topic(
        self, 
        user_id: str, 
        document_id: str, 
        target_topic_path: str = None
    ) -> Result:
        """移动文档到指定主题"""
        try:
            # 1. 验证文档存在
            doc_meta = await self.meta_manager.get_metadata(user_id, document_id)
            if not doc_meta:
                return Result.fail(
                    ErrorType.RESOURCE_ERROR,
                    f"找不到文档: {document_id}",
                    {"user_id": user_id, "document_id": document_id}
                )
            
            # 2. 获取当前主题路径
            current_topic_path = doc_meta.get("topic_path")
            
            # 3. 文档目录名称
            doc_folder_name = self.meta_manager.get_document_folder_name(document_id)
            
            # 4. 当前和目标物理路径
            source_dir = self.meta_manager.get_document_path(user_id, current_topic_path, document_id)
            target_dir = self.meta_manager.get_document_path(user_id, target_topic_path, document_id)
            
            # 5. 如果已在目标位置，直接返回
            if str(source_dir) == str(target_dir):
                return Result.ok(doc_meta)
            
            # 6. 执行物理移动
            if source_dir.exists():
                # 如果目标已存在，先删除
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                    
                # 确保目标父目录存在
                target_dir.parent.mkdir(parents=True, exist_ok=True)
                
                # 移动文档目录
                shutil.move(str(source_dir), str(target_dir))
            else:
                return Result.fail(
                    ErrorType.FILE_ERROR,
                    f"文档物理目录不存在",
                    {"user_id": user_id, "document_id": document_id}
                )
            
            # 7. 更新元数据
            updated_meta = await self.meta_manager.update_metadata(
                user_id, document_id, {"topic_path": target_topic_path}
            )
            
            return Result.ok(updated_meta or doc_meta)
            
        except Exception as e:
            error_type, error_message, error_detail = self._classify_exception(e)
            self.logger.error(f"移动文档失败: {error_message}", exc_info=True)
            error_detail["user_id"] = user_id
            error_detail["document_id"] = document_id
            return Result.fail(error_type, error_message, error_detail)

    # 辅助方法：分类和处理异常
    def _classify_exception(self, e: Exception) -> Tuple[ErrorType, str, Dict[str, Any]]:
        """根据异常类型分类错误"""
        error_detail = {"exception_type": e.__class__.__name__}
        
        if isinstance(e, ValueError):
            return ErrorType.VALIDATION_ERROR, str(e), error_detail
        elif isinstance(e, FileNotFoundError):
            return ErrorType.FILE_ERROR, f"找不到文件: {str(e)}", error_detail
        elif isinstance(e, PermissionError):
            return ErrorType.FILE_ERROR, f"文件权限错误: {str(e)}", error_detail
        else:
            return ErrorType.UNKNOWN_ERROR, f"发生未知错误: {str(e)}", error_detail

    async def list_user_collections(self, user_id: str) -> Result:
        """列出用户拥有的所有向量嵌入集合"""
        try:
            # 委托给处理器执行实际操作
            collections = await self.processor.list_user_collections(user_id)
            
            # 增加summaries集合的检查（如果存在）
            summaries_collection = "summaries"
            if self.processor.retriever:
                try:
                    # 检查summaries集合中是否有该用户的向量
                    stats = await self.processor.retriever.get_stats(summaries_collection)
                    if stats:
                        # 添加到结果中
                        collections.append({
                            "collection_name": summaries_collection,
                            "topic_name": "文档摘要",
                            "vectors_count": stats.get(summaries_collection, {}).get("total_vectors", 0),
                            "document_count": stats.get(summaries_collection, {}).get("unique_documents", 0),
                            "is_system": True  # 标记为系统集合
                        })
                except Exception as e:
                    self.logger.debug(f"检查摘要集合失败: {e}")  # 这不是严重错误，用debug级别即可
            
            return Result.ok({
                "collections": collections,
                "total": len(collections)
            })
        except Exception as e:
            error_type, error_message, error_detail = self._classify_exception(e)
            self.logger.error(f"获取用户集合失败: {error_message}", exc_info=True)
            error_detail["user_id"] = user_id
            return Result.fail(error_type, error_message, error_detail)
