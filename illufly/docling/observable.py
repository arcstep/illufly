"""可观测的文档处理管道模块

提供可观测的文档处理管道实现，包括：
1. 基础可观测管道
2. PDF专用可观测管道
3. 文档处理进度监控
"""

import logging
import time
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path

try:
    from docling.pipeline.base_pipeline import BasePipeline
    from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.document import ConversionResult, InputDocument
    from docling.datamodel.base_models import ConversionStatus
    DOCLING_AVAILABLE = True
except ImportError:
    DOCLING_AVAILABLE = False

from .base import DocumentProcessStage, DocumentProcessStatus

logger = logging.getLogger(__name__)

class ObservablePipeline(BasePipeline):
    """基础可观测文档处理管道"""
    
    def __init__(self, status_tracker: DocumentProcessStatus):
        """初始化可观测管道
        
        Args:
            status_tracker: 处理状态追踪器
        """
        self.status_tracker = status_tracker
        self.last_log_time = time.time()
        self.log_interval = 1.0  # 日志记录间隔（秒）
        self._progress_task = None
        self._processing = False
        self._current_stage = DocumentProcessStage.INITIALIZED
        self._current_progress = 0.0
        self._current_message = ""
        self.intermediate_results: Dict[str, Any] = {
            "pages_processed": 0,
            "total_pages": 0,
            "current_text": "",
            "page_texts": []
        }
    
    def _log_progress(self, stage: DocumentProcessStage, progress: float, message: str):
        """记录处理进度"""
        current_time = time.time()
        self._current_stage = stage
        self._current_progress = progress
        self._current_message = message
        
        if current_time - self.last_log_time >= self.log_interval:
            logger.info(f"文档处理[{self.status_tracker.doc_id}]: {stage.value} - {progress:.1%} - {message}")
            self.status_tracker.update(stage, progress, message)
            self.last_log_time = current_time
    
    async def _progress_monitor(self):
        """进度监控任务"""
        try:
            while self._processing and not self.status_tracker.cancelled:
                current_time = time.time()
                if current_time - self.last_log_time >= 3.0:
                    time_elapsed = current_time - self.status_tracker.start_time
                    message = f"{self._current_message} (已处理 {int(time_elapsed)}秒)"
                    
                    if self.intermediate_results["current_text"]:
                        preview_len = min(len(self.intermediate_results["current_text"]), 100)
                        preview = self.intermediate_results["current_text"][:preview_len] + "..." if preview_len == 100 else ""
                        message += f" | 已解析内容: {self.intermediate_results['pages_processed']}/{self.intermediate_results['total_pages']}页"
                        if preview:
                            message += f" | 内容预览: {preview}"
                    
                    logger.info(f"文档处理[{self.status_tracker.doc_id}]: {self._current_stage.value} - 处理中... {message}")
                    self.status_tracker.update(self._current_stage, self._current_progress, message)
                    self.last_log_time = current_time
                
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"进度监控任务异常: {str(e)}")

class ObservablePdfPipeline(StandardPdfPipeline):
    """PDF专用可观测处理管道"""
    
    def __init__(self, pipeline_options: PdfPipelineOptions, status_tracker: DocumentProcessStatus):
        """初始化PDF可观测管道
        
        Args:
            pipeline_options: PDF处理选项
            status_tracker: 处理状态追踪器
        """
        super().__init__(pipeline_options)
        self.status_tracker = status_tracker
        self.last_log_time = time.time()
        self.log_interval = 1.0
        self._progress_task = None
        self._processing = False
        self._current_stage = DocumentProcessStage.INITIALIZED
        self._current_progress = 0.0
        self._current_message = ""
        self.intermediate_results = {
            "pages_processed": 0,
            "total_pages": 0,
            "current_text": "",
            "page_texts": []
        }
    
    def _log_progress(self, stage: DocumentProcessStage, progress: float, message: str):
        """记录处理进度"""
        current_time = time.time()
        self._current_stage = stage
        self._current_progress = progress
        self._current_message = message
        
        if current_time - self.last_log_time >= self.log_interval:
            logger.info(f"PDF处理[{self.status_tracker.doc_id}]: {stage.value} - {progress:.1%} - {message}")
            self.status_tracker.update(stage, progress, message)
            self.last_log_time = current_time
    
    async def _progress_monitor(self):
        """PDF进度监控任务"""
        try:
            while self._processing and not self.status_tracker.cancelled:
                current_time = time.time()
                if current_time - self.last_log_time >= 3.0:
                    time_elapsed = current_time - self.status_tracker.start_time
                    message = f"{self._current_message} (已处理 {int(time_elapsed)}秒)"
                    
                    if self.intermediate_results["current_text"]:
                        preview_len = min(len(self.intermediate_results["current_text"]), 100)
                        preview = self.intermediate_results["current_text"][:preview_len] + "..." if preview_len == 100 else ""
                        message += f" | 已解析页面: {self.intermediate_results['pages_processed']}/{self.intermediate_results['total_pages']}"
                        if preview:
                            message += f" | 内容预览: {preview}"
                    
                    logger.info(f"PDF处理[{self.status_tracker.doc_id}]: {self._current_stage.value} - 处理中... {message}")
                    self.status_tracker.update(self._current_stage, self._current_progress, message)
                    self.last_log_time = current_time
                
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"PDF进度监控任务异常: {str(e)}")
    
    def execute(self, in_doc: InputDocument, raises_on_error: bool) -> ConversionResult:
        """执行PDF文档处理"""
        conv_res = ConversionResult(input=in_doc)
        
        # 初始化中间结果
        if hasattr(in_doc, 'page_count'):
            self.intermediate_results["total_pages"] = in_doc.page_count
        else:
            try:
                if hasattr(in_doc, 'backend') and hasattr(in_doc.backend, 'get_page_count'):
                    self.intermediate_results["total_pages"] = in_doc.backend.get_page_count()
            except:
                self.intermediate_results["total_pages"] = 0
        
        # 启动进度监控
        self._processing = True
        loop = asyncio.get_event_loop()
        self._progress_task = asyncio.ensure_future(self._progress_monitor())
        
        logger.info(f"开始处理PDF文档 {in_doc.file.name} [{self.status_tracker.doc_id}]")
        self._log_progress(DocumentProcessStage.LOADING, 0.1, f"加载PDF文档 {in_doc.file.name}")
        
        try:
            # 构建文档阶段
            self._log_progress(DocumentProcessStage.BUILDING, 0.2, "构建PDF文档结构")
            conv_res = self._build_document(conv_res)
            
            if self.status_tracker.cancelled:
                logger.info(f"用户取消了PDF处理 [{self.status_tracker.doc_id}]")
                return conv_res
                
            # 组装文档阶段
            self._log_progress(DocumentProcessStage.ASSEMBLING, 0.5, "组装PDF文档内容")
            conv_res = self._assemble_document(conv_res)
            
            if self.status_tracker.cancelled:
                logger.info(f"用户取消了PDF处理 [{self.status_tracker.doc_id}]")
                return conv_res
                
            # 富化文档阶段
            self._log_progress(DocumentProcessStage.ENRICHING, 0.7, "处理PDF文档特殊元素")
            conv_res = self._enrich_document(conv_res)
            
            # 确定最终状态
            conv_res.status = self._determine_status(conv_res)
            self._log_progress(DocumentProcessStage.EXPORTING, 0.9, f"导出PDF文档，状态: {conv_res.status}")
            
        except Exception as e:
            conv_res.status = ConversionStatus.FAILURE
            error_msg = f"PDF处理失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.status_tracker.fail(str(e))
            if raises_on_error:
                raise e
        finally:
            # 停止进度监控
            self._processing = False
            if self._progress_task and not self._progress_task.done():
                self._progress_task.cancel()
                try:
                    loop.run_until_complete(asyncio.gather(self._progress_task, return_exceptions=True))
                except:
                    pass
            
            self._unload(conv_res)
            
        return conv_res 