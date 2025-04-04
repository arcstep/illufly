"""文档处理基础模块

提供文档处理的基本类和接口，包括：
1. 文档处理状态管理
2. 文档处理阶段定义
3. 基础文档处理器接口
"""

import logging
import os
import sys
import time
import uuid
import asyncio
from enum import Enum
from typing import List, Dict, Any, Optional, Union, Tuple
from pathlib import Path
import aiofiles
import aiohttp
from pydantic import BaseModel, Field
import mimetypes
import json
import threading

# docling导入
try:
    from docling.document_converter import DocumentConverter
    from docling.datamodel.pipeline_options import (
        PipelineOptions, 
        PdfPipelineOptions, 
        PictureDescriptionApiOptions
    )
    from docling.datamodel.base_models import ConversionStatus
    from docling.datamodel.document import ConversionResult, InputDocument
    from docling.datamodel.settings import DocumentLimits, PageRange
    from docling.pipeline.base_pipeline import BasePipeline, PaginatedPipeline
    from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
    from docling.utils.profiling import TimeRecorder, ProfilingScope
    from docling.backend.abstract_backend import AbstractDocumentBackend
    from docling.backend.pdf_backend import PdfDocumentBackend
    from docling.backend.msword_backend import MsWordDocumentBackend
    DOCLING_AVAILABLE = True
except ImportError:
    DOCLING_AVAILABLE = False

from ..rocksdb import IndexedRocksDB

logger = logging.getLogger(__name__)

class DocumentProcessStage(str, Enum):
    """文档处理阶段枚举"""
    INITIALIZED = "initialized"       # 初始化
    DOWNLOADING = "downloading"       # 下载中
    LOADING = "loading"               # 加载中
    PARSING = "parsing"               # 解析中
    BUILDING = "building"             # 构建中
    ASSEMBLING = "assembling"         # 组装中
    ENRICHING = "enriching"           # 富化中
    EXPORTING = "exporting"           # 导出中
    CHUNKING = "chunking"             # 分块中
    VECTORIZING = "vectorizing"       # 向量化中
    STORING = "storing"               # 存储中
    COMPLETED = "completed"           # 完成
    FAILED = "failed"                 # 失败

class DocumentProcessStatus(BaseModel):
    """文档处理状态"""
    doc_id: str
    user_id: str
    stage: DocumentProcessStage = DocumentProcessStage.INITIALIZED
    progress: float = 0.0  # 0-1之间的进度
    message: str = ""
    start_time: float = Field(default_factory=time.time)
    update_time: float = Field(default_factory=time.time)
    end_time: Optional[float] = None
    error: Optional[str] = None
    cancellable: bool = True
    cancelled: bool = False
    
    @property
    def duration(self) -> float:
        """获取处理持续时间（秒）"""
        end = self.end_time or time.time()
        return end - self.start_time
    
    def update(self, stage: DocumentProcessStage, progress: float, message: str = ""):
        """更新处理状态"""
        self.stage = stage
        self.progress = progress
        self.message = message
        self.update_time = time.time()
        return self
    
    def complete(self, message: str = "处理完成"):
        """标记为完成状态"""
        self.stage = DocumentProcessStage.COMPLETED
        self.progress = 1.0
        self.message = message
        self.update_time = time.time()
        self.end_time = time.time()
        self.cancellable = False
        return self
    
    def fail(self, error: str):
        """标记为失败状态"""
        self.stage = DocumentProcessStage.FAILED
        self.message = f"处理失败: {error}"
        self.error = error
        self.update_time = time.time()
        self.end_time = time.time()
        self.cancellable = False
        return self
    
    def cancel(self):
        """取消处理"""
        if self.cancellable:
            self.cancelled = True
            self.message = "用户取消处理"
            self.update_time = time.time()
            self.end_time = time.time()
            return True
        return False

class DocumentProcessor:
    """文档处理器，结合docling的自定义pipeline实现文档处理"""
    
    def __init__(self, db: IndexedRocksDB = None):
        """初始化文档处理器
        
        Args:
            db: 索引数据库，用于存储文档内容和状态
        """
        self.db = db
        
        # 任务管理
        self._tasks_lock = threading.Lock()
        self._active_tasks = {}  # {doc_id: (converter, status)}
        
        # docling配置
        self._docling_pipeline_options = None
        if DOCLING_AVAILABLE:
            self._docling_pipeline_options = PipelineOptions()
    
    def _get_status_key(self, user_id: str, doc_id: str) -> str:
        """获取状态存储键"""
        return f"doc_process:{user_id}:{doc_id}"
    
    async def process_document(self, user_id: str, source_path: str, doc_id: str = None) -> Tuple[str, DocumentProcessStatus]:
        """异步处理文档
        
        Args:
            user_id: 用户ID
            source_path: 文档路径或URL
            doc_id: 可选的文档ID，如果不提供则自动生成
            
        Returns:
            文档ID和处理状态
        """
        # 如果未提供文档ID，则自动生成
        if not doc_id:
            doc_id = str(uuid.uuid4())
        
        # 创建处理状态
        status = DocumentProcessStatus(
            doc_id=doc_id,
            user_id=user_id,
            stage=DocumentProcessStage.INITIALIZED,
            progress=0.0,
            message=f"初始化文档处理: {source_path}"
        )
        
        # 保存状态到数据库
        if self.db:
            status_key = self._get_status_key(user_id, doc_id)
            await self.db.put(status_key, json.dumps(status.model_dump()))
        
        # 创建处理任务
        task = asyncio.create_task(
            self._process_document_task(user_id, source_path, doc_id, status)
        )
        
        # 注册处理任务
        with self._tasks_lock:
            # 确保之前的任务已完成
            if doc_id in self._active_tasks:
                logger.warning(f"替换了正在处理的文档 [{doc_id}]")
                
            # 保存任务状态，但转换器将在_process_document_task中创建
            # self._active_tasks[doc_id] = (None, status)
        
        return doc_id, status
    
    async def _process_document_task(self, user_id: str, source_path: str, doc_id: str, status: DocumentProcessStatus) -> None:
        """文档处理任务
        
        Args:
            user_id: 用户ID
            source_path: 文档路径或URL
            doc_id: 文档ID
            status: 处理状态
        """
        logger.info(f"开始文档处理任务 [{doc_id}]: {source_path}")
        
        # 创建转换器实例
        converter = CustomDocumentConverter(status)
        
        # 注册任务
        with self._tasks_lock:
            self._active_tasks[doc_id] = (converter, status)
        
        try:
            # 文档转换
            result, markdown_text = await converter.convert_document(source_path)
            
            # 保存结果到数据库
            if self.db:
                content_key = f"doc:{doc_id}:content"
                results_key = f"doc:{doc_id}:results"
                
                # 保存文档内容
                await self.db.put(content_key, markdown_text)
                
                # 保存处理结果和中间结果
                results_data = {
                    "conversion_status": str(result.status) if hasattr(result, 'status') else "unknown",
                    "doc_id": doc_id,
                    "user_id": user_id,
                    "source_path": source_path,
                    "processing_time": status.duration,
                    "timestamp": time.time(),
                    "intermediate_results": converter._intermediate_results
                }
                
                await self.db.put(results_key, json.dumps(results_data))
                
            # 完成处理
            status.complete(f"文档处理完成")
            logger.info(f"文档处理任务完成 [{doc_id}]: {len(markdown_text) if markdown_text else 0} 字符")
            
        except asyncio.CancelledError:
            logger.info(f"文档处理任务被取消 [{doc_id}]")
            if not status.cancelled:
                status.cancel()
            raise
        except Exception as e:
            error_msg = f"文档处理任务异常 [{doc_id}]: {str(e)}"
            logger.error(error_msg)
            import traceback
            logger.error(traceback.format_exc())
            status.fail(error_msg)
            
            # 尝试保存错误信息和中间结果到数据库
            if self.db:
                results_key = f"doc:{doc_id}:results"
                error_data = {
                    "error": str(e),
                    "doc_id": doc_id,
                    "user_id": user_id,
                    "source_path": source_path,
                    "processing_time": status.duration,
                    "timestamp": time.time(),
                    "intermediate_results": converter._intermediate_results if hasattr(converter, "_intermediate_results") else {}
                }
                await self.db.put(results_key, json.dumps(error_data))
        finally:
            # 清理任务
            with self._tasks_lock:
                if doc_id in self._active_tasks:
                    del self._active_tasks[doc_id]
            
            # 延迟清理任务，保留状态一段时间
            async def delayed_cleanup():
                await asyncio.sleep(3600)  # 保留状态1小时
                if self.db:
                    status_key = self._get_status_key(user_id, doc_id)
                    try:
                        await self.db.delete(status_key)
                    except:
                        pass
            
            asyncio.create_task(delayed_cleanup())
    
    def _get_converter_for_task(self, doc_id: str) -> Optional[CustomDocumentConverter]:
        """获取任务关联的转换器实例
        
        Args:
            doc_id: 文档ID
            
        Returns:
            转换器实例，如果不存在则返回None
        """
        # 从活动任务中获取转换器
        with self._tasks_lock:
            if doc_id in self._active_tasks:
                converter, _ = self._active_tasks[doc_id]
                return converter
        return None
    
    async def get_status(self, user_id: str, doc_id: str) -> Optional[DocumentProcessStatus]:
        """获取文档处理状态
        
        Args:
            user_id: 用户ID
            doc_id: 文档ID
            
        Returns:
            处理状态，如果不存在则返回None
        """
        # 优先从内存中获取
        with self._tasks_lock:
            if doc_id in self._active_tasks:
                _, status = self._active_tasks[doc_id]
                return status
        
        # 从数据库获取
        if self.db:
            status_key = self._get_status_key(user_id, doc_id)
            status_data = await self.db.get(status_key)
            if status_data:
                try:
                    status_dict = json.loads(status_data)
                    return DocumentProcessStatus.model_validate(status_dict)
                except (json.JSONDecodeError, Exception) as e:
                    logger.error(f"解析状态数据失败: {e}")
        
        return None
    
    async def cancel_processing(self, user_id: str, doc_id: str) -> bool:
        """取消文档处理
        
        Args:
            user_id: 用户ID
            doc_id: 文档ID
            
        Returns:
            是否成功取消
        """
        logger.info(f"尝试取消文档处理 [{doc_id}]")
        
        # 获取状态
        status = await self.get_status(user_id, doc_id)
        if not status:
            logger.warning(f"尝试取消未知文档处理 [{doc_id}]")
            return False
            
        # 检查是否可取消
        if not status.cancellable:
            logger.warning(f"文档处理不可取消 [{doc_id}]")
            return False
            
        # 如果已完成或失败，无需取消
        if status.stage in [DocumentProcessStage.COMPLETED, DocumentProcessStage.FAILED]:
            logger.info(f"文档处理已{status.stage.value}，无需取消 [{doc_id}]")
            return True
            
        # 更新状态
        status.cancel()
        
        # 保存状态到数据库
        if self.db:
            status_key = self._get_status_key(user_id, doc_id)
            await self.db.put(status_key, json.dumps(status.model_dump()))
        
        # 尝试终止任务
        with self._tasks_lock:
            if doc_id in self._active_tasks:
                logger.info(f"已取消文档处理任务 [{doc_id}]")
                return True
                
        logger.warning(f"未找到要取消的文档处理任务 [{doc_id}]")
        return False
    
    async def get_document_content(self, user_id: str, doc_id: str) -> Optional[str]:
        """获取处理后的文档内容
        
        Args:
            user_id: 用户ID
            doc_id: 文档ID
            
        Returns:
            文档内容，如果不存在则返回None
        """
        if not self.db:
            return None
            
        # 尝试新键名格式
        content_key = f"doc:{doc_id}:content"
        content = await self.db.get(content_key)
        if content:
            return content
            
        # 兼容旧键名格式
        old_key = f"doc_content:{user_id}:{doc_id}"
        return await self.db.get(old_key)
    
    async def list_processing_documents(self, user_id: str) -> List[DocumentProcessStatus]:
        """列出用户所有的处理中文档
        
        Args:
            user_id: 用户ID
            
        Returns:
            处理状态列表
        """
        result = []
        
        # 查询数据库
        if self.db:
            prefix = f"doc_process:{user_id}:"
            try:
                status_pairs = await self.db.pairs(prefix=prefix)
                for _key, status_data in status_pairs:
                    try:
                        status_dict = json.loads(status_data)
                        status = DocumentProcessStatus.model_validate(status_dict)
                        result.append(status)
                    except Exception as e:
                        logger.error(f"解析状态数据失败: {e}")
            except Exception as e:
                logger.error(f"获取文档状态列表失败: {e}")
        
        # 添加内存中的活动任务
        with self._tasks_lock:
            for doc_id, task_tuple in self._active_tasks.items():
                _, status = task_tuple
                if status.user_id == user_id and not any(s.doc_id == doc_id for s in result):
                    result.append(status)
        
        return result
    
    async def get_intermediate_results(self, user_id: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """获取文档处理的中间结果
        
        Args:
            user_id: 用户ID
            doc_id: 文档ID
            
        Returns:
            中间结果字典，如果不存在则返回None
        """
        try:
            # 获取当前任务的转换器
            converter = self._get_converter_for_task(doc_id)
            if converter:
                # 直接返回转换器的中间结果
                return {
                    "intermediate_results": converter._intermediate_results
                }
            
            # 如果找不到转换器，尝试从数据库获取
            status = await self.get_status(user_id, doc_id)
            if not status:
                return None
                
            # 如果处理已完成或失败，尝试从数据库中检索内容和任何保存的中间结果
            if status.stage in [DocumentProcessStage.COMPLETED, DocumentProcessStage.FAILED]:
                # 构建结果键
                results_key = f"doc:{doc_id}:results"
                
                # 获取结果
                if self.db:
                    results_data = await self.db.get(results_key)
                    if results_data:
                        # 尝试解析结果
                        try:
                            results = json.loads(results_data)
                            if "intermediate_results" in results:
                                return {
                                    "intermediate_results": results["intermediate_results"]
                                }
                        except json.JSONDecodeError:
                            pass
            
            # 返回空结果
            return {"intermediate_results": {}}
            
        except Exception as e:
            logger.error(f"获取中间结果异常 [{doc_id}]: {str(e)}")
            return {"intermediate_results": {}, "error": str(e)} 