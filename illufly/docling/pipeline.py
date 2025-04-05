"""可观测管道包装器

使用装饰器模式包装任何BasePipeline实例，为其增加可观测性。
这使得我们可以为任何文档格式添加状态跟踪和异步观测能力。
"""

import logging
import time
import asyncio
from typing import Dict, Any, Optional, Callable, AsyncGenerator, Union, List, Type, Tuple
from pathlib import Path
from functools import partial
from copy import deepcopy

# 从官方docling导入
from docling.pipeline.base_pipeline import BasePipeline
from docling.datamodel.document import ConversionResult, InputDocument
from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.pipeline.simple_pipeline import SimplePipeline

# 导入自定义状态跟踪组件
from .schemas import DocumentProcessStage, DocumentProcessStatus

logger = logging.getLogger(__name__)


class ObservablePipelineWrapper:
    """通用的可观测管道包装器
    
    使用装饰器模式包装任何BasePipeline实例，为其增加可观测性。
    这使得我们可以为任何文档格式添加状态跟踪和异步观测能力。
    """
    
    def __init__(self, pipeline: BasePipeline, status_tracker: DocumentProcessStatus):
        """初始化可观测管道包装器
        
        Args:
            pipeline: 要观测的原始管道对象
            status_tracker: 状态跟踪器
        """
        self.pipeline = pipeline
        self.status_tracker = status_tracker
        self.last_log_time = time.time()
        self.log_interval = 1.0  # 日志记录间隔（秒）
        self._progress_task = None
        self._processing = False
        self._current_stage = DocumentProcessStage.INIT
        self._current_progress = 0.0
        self._current_message = ""
        self._result = None  # 存储异步处理的结果
        self.intermediate_results: Dict[str, Any] = {
            "pages_processed": 0,
            "total_pages": 0,
            "current_text": "",
            "page_texts": []
        }
        
        # 保存原始方法的引用
        self._original_methods = {
            "_build_document": getattr(self.pipeline, "_build_document", None),
            "_assemble_document": getattr(self.pipeline, "_assemble_document", None),
            "_enrich_document": getattr(self.pipeline, "_enrich_document", None),
            "_determine_status": getattr(self.pipeline, "_determine_status", None),
            "_unload": getattr(self.pipeline, "_unload", None)
        }
        
        # 替换为监控版本方法
        if self._original_methods["_build_document"]:
            self.pipeline._build_document = self._wrap_method(
                self._original_methods["_build_document"], 
                DocumentProcessStage.BUILD, 
                0.3, 
                "构建文档结构"
            )
        
        if self._original_methods["_assemble_document"]:
            self.pipeline._assemble_document = self._wrap_method(
                self._original_methods["_assemble_document"], 
                DocumentProcessStage.ASSEMBLE, 
                0.6, 
                "组装文档内容"
            )
        
        if self._original_methods["_enrich_document"]:
            self.pipeline._enrich_document = self._wrap_method(
                self._original_methods["_enrich_document"], 
                DocumentProcessStage.ENRICH, 
                0.8, 
                "处理文档特殊元素"
            )
        
        if self._original_methods["_determine_status"]:
            self.pipeline._determine_status = self._wrap_status_method(
                self._original_methods["_determine_status"]
            )
        
        if self._original_methods["_unload"]:
            self.pipeline._unload = self._wrap_unload_method(
                self._original_methods["_unload"]
            )
    
    def _wrap_method(self, method: Callable, stage: DocumentProcessStage, 
                     progress: float, message: str) -> Callable:
        """包装管道方法，添加进度追踪
        
        Args:
            method: 原始方法
            stage: 对应的处理阶段
            progress: 阶段进度值
            message: 状态消息
            
        Returns:
            包装后的方法
        """
        def wrapped(conv_res: ConversionResult) -> ConversionResult:
            # 记录开始
            self._log_progress(stage, progress, message)
            
            # 执行原始方法
            result = method(conv_res)
            
            # 更新中间结果 - 根据文档类型收集不同信息
            if stage == DocumentProcessStage.BUILD:
                if hasattr(conv_res, 'pages') and len(conv_res.pages) > 0:
                    self.intermediate_results["total_pages"] = len(conv_res.pages)
                    self.intermediate_results["pages_processed"] = len(conv_res.pages)
            elif stage == DocumentProcessStage.ASSEMBLE:
                if hasattr(conv_res, 'document') and conv_res.document:
                    # 尝试提取文本内容
                    try:
                        text_content = conv_res.document.export_to_text()
                        if text_content:
                            self.intermediate_results["current_text"] = text_content
                    except Exception as e:
                        logger.warning(f"无法导出文本: {str(e)}")
            
            return result
        
        return wrapped
    
    def _wrap_status_method(self, method: Callable) -> Callable:
        """包装状态判断方法
        
        Args:
            method: 原始方法
            
        Returns:
            包装后的方法
        """
        def wrapped(conv_res: ConversionResult) -> ConversionStatus:
            # 执行原始方法
            status = method(conv_res)
            
            # 记录状态信息
            self._log_progress(
                DocumentProcessStage.COMPLETE if status == ConversionStatus.SUCCESS else DocumentProcessStage.ERROR,
                0.9,
                f"完成文档处理，状态: {status}"
            )
            
            return status
        
        return wrapped
    
    def _wrap_unload_method(self, method: Callable) -> Callable:
        """包装资源释放方法
        
        Args:
            method: 原始方法
            
        Returns:
            包装后的方法
        """
        def wrapped(conv_res: ConversionResult):
            # 执行原始方法，增加错误处理
            try:
                result = method(conv_res)
            except AttributeError as e:
                # 处理"NoneType" object has no attribute 'close'错误
                if "'NoneType' object has no attribute" in str(e):
                    logger.warning(f"资源释放时遇到已知问题：{str(e)}，这通常是因为文档未成功加载或后端未正确初始化")
                    # 继续执行不中断
                else:
                    # 其他AttributeError记录为警告但不抛出
                    logger.warning(f"资源释放时遇到属性错误：{str(e)}")
            except Exception as e:
                logger.warning(f"资源释放过程中出现异常: {str(e)}")
                # 不再抛出异常，避免因为资源清理问题影响整个流程
            
            # 停止监控
            self._processing = False
            if self._progress_task and not self._progress_task.done():
                self._progress_task.cancel()
            
            # 更新状态为完成
            if conv_res.status == ConversionStatus.SUCCESS:
                self.status_tracker.update(
                    stage=DocumentProcessStage.COMPLETE,
                    progress=1.0,
                    message="文档处理完成"
                )
            
            return conv_res  # 返回转换结果而不是method的结果
        
        return wrapped
    
    def _log_progress(self, stage: DocumentProcessStage, progress: float, message: str):
        """记录处理进度
        
        Args:
            stage: 处理阶段 
            progress: 进度值
            message: 状态消息
        """
        current_time = time.time()
        self._current_stage = stage
        self._current_progress = progress
        self._current_message = message
        
        # 总是更新状态追踪器，确保状态正确反映
        self.status_tracker.update(stage=stage, progress=progress, message=message)
        
        # 只有超过时间间隔才记录日志，以减少日志量
        if current_time - self.last_log_time >= self.log_interval:
            logger.info(f"文档处理[{self.status_tracker.doc_id}]: {stage.value} - {progress:.1%} - {message}")
            self.last_log_time = current_time
    
    async def _progress_monitor(self):
        """进度监控任务"""
        try:
            while self._processing:
                current_time = time.time()
                if current_time - self.last_log_time >= 3.0:
                    time_elapsed = current_time - self.status_tracker.start_time.timestamp() if self.status_tracker.start_time else 0
                    message = f"{self._current_message} (已处理 {int(time_elapsed)}秒)"
                    
                    # 如果有文本内容，提供摘要
                    if self.intermediate_results["current_text"]:
                        preview_len = min(len(self.intermediate_results["current_text"]), 100)
                        preview = self.intermediate_results["current_text"][:preview_len] + "..." if preview_len == 100 else ""
                        message += f" | 已解析内容: {self.intermediate_results['pages_processed']}/{self.intermediate_results['total_pages']}页"
                        if preview:
                            message += f" | 内容预览: {preview}"
                    
                    logger.info(f"文档处理[{self.status_tracker.doc_id}]: {self._current_stage.value} - 处理中... {message}")
                    self.status_tracker.update(stage=self._current_stage, progress=self._current_progress, message=message)
                    self.last_log_time = current_time
                
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            logger.debug(f"监控任务已取消: {self.status_tracker.doc_id}")
        except Exception as e:
            logger.error(f"进度监控任务异常: {str(e)}")
    
    def start_monitoring(self):
        """开始监控"""
        self._processing = True
        
        # 获取或创建事件循环
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # 检查是否已在运行的监控任务
        if self._progress_task and not self._progress_task.done():
            logger.debug(f"已存在运行中的监控任务: {self.status_tracker.doc_id}")
            return self._progress_task
        
        # 创建监控任务
        monitor_task = loop.create_task(self._progress_monitor())
        
        # 为任务添加完成回调，以避免"coroutine was never awaited"警告
        def _done_callback(future):
            try:
                # 检查任务是否有异常
                if future.exception():
                    logger.warning(f"监控任务异常: {future.exception()}")
            except (asyncio.CancelledError, asyncio.InvalidStateError):
                # 任务被取消或无效状态是正常的
                pass
        
        monitor_task.add_done_callback(_done_callback)
        self._progress_task = monitor_task
        return monitor_task
    
    def stop_monitoring(self):
        """停止监控"""
        self._processing = False
        if self._progress_task and not self._progress_task.done():
            logger.debug(f"正在取消监控任务: {self.status_tracker.doc_id}")
            self._progress_task.cancel()
    
    def execute(self, in_doc: InputDocument, raises_on_error: bool = True) -> ConversionResult:
        """执行文档处理
        
        Args:
            in_doc: 输入文档
            raises_on_error: 错误时是否抛出异常
            
        Returns:
            转换结果
        """
        # 初始化中间结果
        if hasattr(in_doc, 'page_count') and in_doc.page_count:
            self.intermediate_results["total_pages"] = in_doc.page_count
        
        # 启动进度监控
        self.start_monitoring()
        
        logger.info(f"开始处理文档 {in_doc.file.name if hasattr(in_doc, 'file') and hasattr(in_doc.file, 'name') else 'unknown'} [{self.status_tracker.doc_id}]")
        self._log_progress(DocumentProcessStage.INIT, 0.1, f"初始化文档处理")
        
        result = None
        try:
            # 执行原始pipeline的处理
            result = self.pipeline.execute(in_doc, raises_on_error=False)  # 先设置为False以便我们可以控制异常处理
            # 保存结果以便后续获取
            self._result = result
            
            # 如果处理成功，返回结果
            if result.status == ConversionStatus.SUCCESS:
                return result
            
            # 如果处理失败但用户要求不抛出异常，直接返回失败结果
            if not raises_on_error:
                error_msg = f"文档处理失败: {result.status}"
                logger.warning(error_msg)
                self.status_tracker.update(stage=DocumentProcessStage.ERROR, progress=0.0, message=error_msg)
                return result
                
            # 如果处理失败且用户要求抛出异常，抛出自定义异常
            error_msg = f"文档处理失败: {result.status}"
            logger.error(error_msg)
            self.status_tracker.update(stage=DocumentProcessStage.ERROR, progress=0.0, message=error_msg, error=error_msg)
            raise RuntimeError(error_msg)
            
        except Exception as e:
            error_msg = f"文档处理失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.status_tracker.update(stage=DocumentProcessStage.ERROR, progress=0.0, error=str(e))
            
            if raises_on_error:
                raise
            
            # 如果出现异常且不抛出，返回失败结果
            if result is None:
                # 如果没有result，创建一个失败的ConversionResult
                return ConversionResult(input=in_doc, status=ConversionStatus.FAILURE, errors=[str(e)])
            # 如果已有result，直接返回
            return result
        finally:
            # 确保停止监控
            self.stop_monitoring()
    
    async def execute_async(self, in_doc: InputDocument, raises_on_error: bool = True) -> AsyncGenerator[Dict[str, Any], None]:
        """异步执行文档处理并产生状态更新
        
        Args:
            in_doc: 输入文档
            raises_on_error: 错误时是否抛出异常
            
        Yields:
            状态更新和处理结果
        """
        # 初始化中间结果
        if hasattr(in_doc, 'page_count') and in_doc.page_count:
            self.intermediate_results["total_pages"] = in_doc.page_count
        
        # 启动进度监控
        self.start_monitoring()
        
        # 初始化处理
        logger.info(f"开始处理文档 {in_doc.file.name if hasattr(in_doc, 'file') and hasattr(in_doc.file, 'name') else 'unknown'} [{self.status_tracker.doc_id}]")
        self._log_progress(DocumentProcessStage.INIT, 0.1, f"初始化文档处理")
        
        # 产生初始状态
        yield self.status_tracker.to_dict()
        
        result = None
        error = None
        
        try:
            # 创建一个异步任务执行pipeline处理
            process_task = asyncio.create_task(self._execute_pipeline_async(in_doc, raises_on_error))
            
            # 定期产生状态更新
            last_update_time = time.time()
            while not process_task.done():
                current_time = time.time()
                if current_time - last_update_time >= 0.5:  # 每0.5秒产生一次状态更新
                    yield self.status_tracker.to_dict()
                    last_update_time = current_time
                
                await asyncio.sleep(0.1)
            
            # 获取处理结果
            result = await process_task
            
            # 保存结果以供后续获取
            self._result = result
            
            # 产生最终状态
            if result.status == ConversionStatus.SUCCESS:
                self._log_progress(DocumentProcessStage.COMPLETE, 1.0, "文档处理完成")
            else:
                error_msg = f"文档处理失败: {result.status}"
                self._log_progress(DocumentProcessStage.ERROR, 1.0, error_msg)
                
            yield self.status_tracker.to_dict()
            
            # 返回处理结果
            yield {
                "type": "result",
                "result": result
            }
            
        except Exception as e:
            error = e
            error_msg = f"文档处理过程中出现异常: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.status_tracker.update(stage=DocumentProcessStage.ERROR, progress=1.0, error=str(e))
            
            # 产生错误状态
            yield self.status_tracker.to_dict()
            
            if raises_on_error:
                raise
        finally:
            # 确保停止监控
            self.stop_monitoring()
    
    async def _execute_pipeline_async(self, in_doc: InputDocument, raises_on_error: bool) -> ConversionResult:
        """异步执行pipeline处理
        
        包装同步的execute方法使其可以在异步环境中执行
        
        Args:
            in_doc: 输入文档
            raises_on_error: 错误时是否抛出异常
            
        Returns:
            处理结果
        """
        try:
            # 使用线程池执行同步方法
            loop = asyncio.get_running_loop()
            # 使用我们修改过的execute方法进行调用，它有更强的错误处理能力
            result = await loop.run_in_executor(
                None, 
                lambda: self.execute(in_doc, raises_on_error=False) # 先不抛出异常，由本方法控制
            )
            
            # 检查结果状态
            if result.status != ConversionStatus.SUCCESS and raises_on_error:
                error_msg = f"异步管道处理失败: {result.status}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
                
            return result
            
        except Exception as e:
            logger.error(f"异步执行pipeline过程中出现异常: {str(e)}", exc_info=True)
            if raises_on_error:
                raise
            # 返回失败结果
            return ConversionResult(input=in_doc, status=ConversionStatus.FAILURE, errors=[str(e)]) 