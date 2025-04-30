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
from voidrail import ClientDealer

from ..llm.retriever.lancedb import LanceRetriever
from .sm import DocumentStateMachine
from .processor import DocumentProcessor
from .meta import DocumentMetaManager

# 定义错误类型枚举
class ErrorType(str, Enum):
    VALIDATION_ERROR = "validation_error"  # 验证错误（如状态检查失败）
    FILE_ERROR = "file_error"  # 文件操作错误
    STATE_ERROR = "state_error"  # 状态转换错误
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
    """简化为协调层，主要负责创建状态机和委托处理器执行操作"""
    
    def __init__(
        self, 
        base_dir: str, 
        max_file_size: int = 50 * 1024 * 1024,
        max_total_size_per_user: int = 200 * 1024 * 1024,
        allowed_extensions: List[str] = None,
        voidrail_client = None,
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
            voidrail_client=voidrail_client,
            vector_db_path=str(self.base_dir / "vector_db"),
            embedding_config=embedding_config,
            logger=logger
        )

        self.logger = logger or logging.getLogger(__name__)

    # ==== 状态机管理 ====
    
    async def create_state_machine(self, user_id: str, document_id: str) -> DocumentStateMachine:
        """创建并激活文档状态机实例"""
        machine = DocumentStateMachine(
            meta_manager=self.meta_manager,
            user_id=user_id,
            document_id=document_id,
            logger=self.logger
        )
        await machine.activate_initial_state()
        return machine
    
    # ==== 文档管理 - 委托给处理器 ====
    
    async def create_document(self, user_id: str, doc_info: Dict[str, Any], 
                            topic_path: str = None, metadata: Dict[str, Any] = None) -> Result:
        """创建文档元数据并设置初始状态 - 业务流程起点"""
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
                "state": "init",
                "sub_state": "none",
                "has_markdown": False,
                "has_chunks": False, 
                "has_embeddings": False,
                "has_qa_pairs": False
            }
            
            # 合并用户元数据
            if metadata:
                # 过滤保留字段
                for key in ["document_id", "created_at", "state"]:
                    if key in metadata:
                        del metadata[key]
                meta.update(metadata)
            
            # 保存元数据
            doc_meta = await self.meta_manager.create_document(
                user_id, document_id, topic_path, meta
            )
            
            # 创建状态机并设置相应初始状态
            machine = await self.create_state_machine(user_id, document_id)
            
            # 根据文档类型设置初始状态
            if doc_info.get("source_type") == "remote":
                await machine.set_state("bookmarked", sub_state="completed")
            elif doc_info.get("source_type") == "chat":
                await machine.set_state("saved_chat", sub_state="completed")
            else:
                await machine.set_state("uploaded", sub_state="completed")
                
            # 获取更新后的元数据并返回
            updated_doc_meta = await self.meta_manager.get_metadata(user_id, document_id)
            return Result.ok(updated_doc_meta)
        except Exception as e:
            error_type, error_message, error_detail = self._classify_exception(e)
            self.logger.error(f"创建文档失败: {error_message}", exc_info=True)
            error_detail["user_id"] = user_id
            error_detail["document_id"] = doc_info.get("document_id") if doc_info else None
            return Result.fail(error_type, error_message, error_detail)
        
    async def upload_document(self, user_id: str, file: UploadFile, topic_path: str = None, 
                            metadata: Dict[str, Any] = None) -> Result:
        """上传文档 - 协调文件处理和状态管理"""
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
            
            # 2. 创建文档元数据和设置状态
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
            
            return doc_result
        except Exception as e:
            error_type, error_message, error_detail = self._classify_exception(e)
            self.logger.error(f"上传文档失败: {error_message}", exc_info=True)
            error_detail["user_id"] = user_id
            return Result.fail(error_type, error_message, error_detail)
    
    async def create_bookmark(self, user_id: str, url: str, filename: str, 
                            topic_path: str = None, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """创建网络书签文档 - 协调文档注册和状态管理"""
        # 1. 注册远程文档
        doc_info = await self.processor.register_remote_doc_info(user_id, url, filename)
        
        # 2. 创建文档元数据和设置状态
        return await self.create_document(user_id, doc_info, topic_path, metadata)
    
    async def convert_to_markdown(self, user_id: str, document_id: str) -> Result:
        """转换为Markdown - 协调处理器和状态机"""
        try:
            # 1. 创建状态机
            machine = await self.create_state_machine(user_id, document_id)
            
            # 2. 检查当前状态
            current_state = await machine.get_current_state()
            if current_state not in ["uploaded", "bookmarked"]:
                return Result.fail(
                    ErrorType.STATE_ERROR,
                    f"当前状态 {current_state} 不支持转换为Markdown",
                    {"current_state": current_state, "required_states": ["uploaded", "bookmarked"]}
                )
                
            # 3. 开始处理 - 状态机更新子状态
            await machine.start_processing("markdowned")
            
            try:
                # 4. 执行文件处理 - 处理器负责
                result = await self.processor.convert_document_to_markdown(user_id, document_id)
                
                # 5. 完成处理 - 状态机更新状态
                await machine.complete_processing("markdowned")
                
                return Result.ok({
                    **result,
                    "document_id": document_id,
                    "state": "markdowned",
                    "sub_state": "completed"
                })
            except Exception as process_e:
                # 处理失败 - 状态机记录失败状态
                await machine.fail_processing("markdowned", str(process_e))
                error_type, error_message, error_detail = self._classify_exception(process_e)
                error_detail["user_id"] = user_id
                error_detail["document_id"] = document_id
                return Result.fail(error_type, error_message, error_detail)
        except Exception as e:
            error_type, error_message, error_detail = self._classify_exception(e)
            self.logger.error(f"转换Markdown失败: {error_message}", exc_info=True)
            error_detail["user_id"] = user_id
            error_detail["document_id"] = document_id
            return Result.fail(error_type, error_message, error_detail)
    
    async def chunk_document(self, user_id: str, document_id: str) -> Dict[str, Any]:
        """将文档切分为片段 - 协调处理器和状态机"""
        # 1. 创建状态机
        machine = await self.create_state_machine(user_id, document_id)
        
        # 2. 检查当前状态
        current_state = await machine.get_current_state()
        if current_state != "markdowned":
            raise ValueError(f"当前状态 {current_state} 不支持切片")
            
        try:
            # 3. 开始处理 - 状态机负责状态变更
            await machine.start_processing("chunked")
            
            # 4. 执行切片 - 处理器负责文件操作
            result = await self.processor.process_document_chunks(user_id, document_id)
            
            # 5. 更新元数据中的切片信息 - 处理器负责处理相关元数据
            await self.processor.add_chunks_metadata(user_id, document_id, result["chunks"])
            
            # 6. 完成处理 - 状态机负责状态变更
            await machine.complete_processing("chunked")
            
            return {
                **result,
                "document_id": document_id,
                "state": "chunked",
                "sub_state": "completed"
            }
        except Exception as e:
            # 处理失败 - 状态机负责状态变更
            await machine.fail_processing("chunked", str(e))
            raise
    
    async def generate_embeddings(self, user_id: str, document_id: str) -> Dict[str, Any]:
        """为文档切片生成向量嵌入"""
        # 创建状态机
        machine = await self.create_state_machine(user_id, document_id)
        
        # 检查当前状态
        current_state = await machine.get_current_state()
        if current_state != "chunked":
            raise ValueError(f"当前状态 {current_state} 不支持生成嵌入")
            
        try:
            # 开始处理
            await machine.start_processing("embedded")
            
            # 执行向量化
            result = await self.processor.process_document_embeddings(user_id, document_id)
            
            # 完成处理
            await machine.complete_processing("embedded")
            
            return {
                **result,
                "document_id": document_id,
                "state": "embedded",
                "sub_state": "completed"
            }
        except Exception as e:
            await machine.fail_processing("embedded", str(e))
            raise
    
    async def rollback_to_previous_state(self, user_id: str, document_id: str) -> Dict[str, Any]:
        """回滚到上一个状态 - 协调处理器和状态机"""
        # 1. 创建状态机
        machine = await self.create_state_machine(user_id, document_id)
        
        # 2. 获取当前状态和前一个状态
        current_state = await machine.get_current_state()
        prev_state = machine.get_previous_state()
        
        if not prev_state:
            raise ValueError(f"当前状态 {current_state} 没有前一个状态可回滚")
            
        # 3. 执行资源回滚操作
        if current_state == "markdowned" and prev_state in ["uploaded", "bookmarked"]:
            # 回滚Markdown，删除MD文件
            await self.processor.remove_markdown_file(user_id, document_id)
        elif current_state == "chunked" and prev_state == "markdowned":
            # 回滚切片，删除切片目录
            await self.processor.remove_chunks_dir(user_id, document_id)
        elif current_state == "embedded" and prev_state in ["chunked", "qa_extracted"]:
            # 回滚嵌入，从向量存储中删除
            await self.processor.remove_vector_embeddings(user_id, document_id)
                
        # 4. 执行状态回滚 - 使用状态机
        await machine.rollback_to_previous(details={"rollback_from": current_state})
        
        # 5. 获取更新后的元数据
        return await self.get_document(user_id, document_id)
    
    async def delete_document(self, user_id: str, document_id: str) -> Result:
        """删除文档 - 协调状态管理和资源清理"""
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
                await self.processor.remove_vector_embeddings(user_id, document_id)
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
    
    async def get_document_state(self, user_id: str, document_id: str) -> Dict[str, str]:
        """获取文档当前状态，包括主状态和子状态"""
        machine = await self.create_state_machine(user_id, document_id)
        return await machine.get_current_state_info()

    async def get_markdown_content(self, user_id: str, document_id: str) -> Result:
        """获取文档的Markdown内容
        
        Args:
            user_id: 用户ID
            document_id: 文档ID
            
        Returns:
            Result对象，包含Markdown内容或错误信息
        """
        try:
            # 1. 检查文档元数据
            doc_meta = await self.meta_manager.get_metadata(user_id, document_id)
            if not doc_meta:
                return Result.fail(
                    ErrorType.RESOURCE_ERROR,
                    f"找不到文档: {document_id}",
                    {"user_id": user_id, "document_id": document_id}
                )
            
            # 2. 检查文档状态
            state = doc_meta.get("state", "init")
            if state not in ["markdowned", "chunked", "embedded"]:
                return Result.fail(
                    ErrorType.STATE_ERROR,
                    f"文档当前状态 ({state}) 不支持获取Markdown内容",
                    {"user_id": user_id, "document_id": document_id, "state": state}
                )
            
            # 3. 获取Markdown内容
            content_data = await self.processor.get_markdown_content(user_id, document_id)
            
            # 4. 合并元数据和内容数据
            result = {
                **content_data,
                "title": doc_meta.get("original_name", ""),
                "type": doc_meta.get("type", ""),
                "extension": doc_meta.get("extension", ""),
                "state": state
            }
            
            return Result.ok(result)
        
        except FileNotFoundError as e:
            return Result.fail(
                ErrorType.FILE_ERROR,
                f"找不到Markdown文件: {document_id}",
                {"user_id": user_id, "document_id": document_id}
            )
        except ValueError as e:
            return Result.fail(
                ErrorType.VALIDATION_ERROR,
                str(e),
                {"user_id": user_id, "document_id": document_id}
            )
        except Exception as e:
            error_type, error_message, error_detail = self._classify_exception(e)
            self.logger.error(f"获取文档内容失败: {error_message}", exc_info=True)
            error_detail["user_id"] = user_id
            error_detail["document_id"] = document_id
            return Result.fail(error_type, error_message, error_detail)

    async def get_chunks(self, user_id: str, document_id: str, start_index: int = 0, limit: int = 20) -> Result:
        """获取文档的切片列表
        
        Args:
            user_id: 用户ID
            document_id: 文档ID
            start_index: 开始的切片索引
            limit: 返回的最大切片数量
            
        Returns:
            Result对象，包含切片列表或错误信息
        """
        try:
            # 1. 检查文档元数据
            doc_meta = await self.meta_manager.get_metadata(user_id, document_id)
            if not doc_meta:
                return Result.fail(
                    ErrorType.RESOURCE_ERROR,
                    f"找不到文档: {document_id}",
                    {"user_id": user_id, "document_id": document_id}
                )
            
            # 2. 检查文档状态
            state = doc_meta.get("state", "init")
            if state not in ["chunked", "embedded"]:
                return Result.fail(
                    ErrorType.STATE_ERROR,
                    f"文档当前状态 ({state}) 不支持获取切片内容",
                    {"user_id": user_id, "document_id": document_id, "state": state}
                )
            
            # 3. 获取切片数据
            chunks_data = list(await self.processor.iter_chunks(user_id, document_id))
            
            # 4. 添加文档元数据
            result = {
                **chunks_data,
                "title": doc_meta.get("original_name", ""),
                "type": doc_meta.get("type", ""),
                "state": state
            }
            
            return Result.ok(result)
        
        except FileNotFoundError as e:
            return Result.fail(
                ErrorType.FILE_ERROR,
                f"找不到文档切片: {document_id}",
                {"user_id": user_id, "document_id": document_id}
            )
        except ValueError as e:
            return Result.fail(
                ErrorType.VALIDATION_ERROR,
                str(e),
                {"user_id": user_id, "document_id": document_id}
            )
        except Exception as e:
            error_type, error_message, error_detail = self._classify_exception(e)
            self.logger.error(f"获取文档切片失败: {error_message}", exc_info=True)
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
        elif "state" in str(e).lower():
            return ErrorType.STATE_ERROR, str(e), error_detail
        else:
            return ErrorType.UNKNOWN_ERROR, f"发生未知错误: {str(e)}", error_detail

    async def close(self):
        """关闭服务及其资源"""
        try:
            # 委托处理器关闭资源
            if hasattr(self, 'processor'):
                await self.processor.close()
            
            return True
        except Exception as e:
            self.logger.error(f"关闭服务资源时出错: {str(e)}")
            return False

