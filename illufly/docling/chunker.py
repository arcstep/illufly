"""可观测文档分块器

对文档分块过程进行包装，提供异步处理和状态追踪能力。
"""

import logging
import time
import asyncio
from typing import Dict, Any, Optional, AsyncGenerator, Union, Iterator
from pathlib import Path
from datetime import datetime

# 从官方docling导入
from docling.chunking import BaseChunker, BaseChunk, HybridChunker

# 导入自定义状态跟踪组件
from .schemas import DocumentProcessStage, DocumentProcessStatus

logger = logging.getLogger(__name__)


class ObservableChunker:
    """可观测文档分块器
    
    对文档分块过程进行包装，提供异步处理和状态追踪能力
    """
    
    def __init__(self, chunker: BaseChunker, status_tracker: DocumentProcessStatus):
        """初始化可观测分块器
        
        Args:
            chunker: 基础分块器
            status_tracker: 状态跟踪器
        """
        self.chunker = chunker
        self.status_tracker = status_tracker
        self.last_log_time = time.time()
        self.log_interval = 1.0  # 日志记录间隔（秒）
        self._processing = False
        self._progress_task = None
        self._chunks_processed = 0
        self._total_chunks = 0
        
    def _log_progress(self, progress: float, message: str):
        """记录处理进度
        
        Args:
            progress: 进度值（0.0-1.0）
            message: 状态消息
        """
        current_time = time.time()
        
        # 更新状态追踪器
        self.status_tracker.update(
            stage=DocumentProcessStage.CHUNKING,
            progress=progress,
            message=message
        )
        
        # 只有超过时间间隔才记录日志
        if current_time - self.last_log_time >= self.log_interval:
            logger.info(f"文档分块[{self.status_tracker.doc_id}]: {progress:.1%} - {message}")
            self.last_log_time = current_time
    
    async def _progress_monitor(self):
        """进度监控任务"""
        try:
            while self._processing:
                current_time = time.time()
                if current_time - self.last_log_time >= 3.0:
                    # 计算处理进度
                    progress = 0.1  # 初始进度
                    if self._total_chunks > 0:
                        progress = min(0.9, self._chunks_processed / self._total_chunks * 0.9)
                    
                    time_elapsed = current_time - self.status_tracker.start_time.timestamp() if self.status_tracker.start_time else 0
                    message = f"文档分块中 (已处理 {self._chunks_processed} 个块，耗时 {int(time_elapsed)}秒)"
                    
                    logger.info(f"文档分块[{self.status_tracker.doc_id}]: {progress:.1%} - {message}")
                    self.status_tracker.update(
                        stage=DocumentProcessStage.CHUNKING,
                        progress=progress,
                        message=message
                    )
                    self.last_log_time = current_time
                
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            logger.debug(f"分块监控任务已取消: {self.status_tracker.doc_id}")
        except Exception as e:
            logger.error(f"分块进度监控任务异常: {str(e)}")
    
    def start_monitoring(self):
        """开始监控"""
        self._processing = True
        
        # 获取或创建事件循环
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # 检查是否已有监控任务
        if self._progress_task and not self._progress_task.done():
            logger.debug(f"已存在运行中的分块监控任务: {self.status_tracker.doc_id}")
            return self._progress_task
        
        # 创建监控任务
        monitor_task = loop.create_task(self._progress_monitor())
        
        # 为任务添加完成回调，以避免"coroutine was never awaited"警告
        def _done_callback(future):
            try:
                # 检查任务是否有异常
                if future.exception():
                    logger.warning(f"分块监控任务异常: {future.exception()}")
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
            logger.debug(f"正在取消分块监控任务: {self.status_tracker.doc_id}")
            self._progress_task.cancel()
    
    def chunk(self, document) -> Iterator[BaseChunk]:
        """同步执行文档分块
        
        Args:
            document: docling文档对象
            
        Returns:
            分块结果迭代器
        """
        # 启动监控
        self.start_monitoring()
        
        try:
            # 初始化
            self._log_progress(0.1, "开始文档分块")
            
            # 执行分块
            chunk_iterator = self.chunker.chunk(document)
            
            # 先收集所有块以确定总数（这可能会占用更多内存，但有助于计算进度）
            chunks = list(chunk_iterator)
            self._total_chunks = len(chunks)
            
            # 重新迭代并返回
            for i, chunk in enumerate(chunks):
                self._chunks_processed = i + 1
                progress = 0.1 + 0.8 * (i + 1) / self._total_chunks
                self._log_progress(progress, f"处理块 {i+1}/{self._total_chunks}")
                yield chunk
            
            # 完成
            self._log_progress(1.0, f"文档分块完成，共生成{self._total_chunks}个块")
            
        except Exception as e:
            error_msg = f"文档分块失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.status_tracker.update(
                stage=DocumentProcessStage.ERROR,
                progress=0.0,
                error=str(e)
            )
            raise
        finally:
            # 确保停止监控
            self.stop_monitoring()
    
    async def chunk_async(self, document) -> AsyncGenerator[Dict[str, Any], None]:
        """异步执行文档分块并产生状态更新和结果
        
        Args:
            document: docling文档对象
            
        Yields:
            状态更新和分块结果
        """
        # 启动监控
        self.start_monitoring()
        
        # 初始化
        self._log_progress(0.1, "开始文档分块")
        yield self.status_tracker.to_dict()
        
        try:
            # 使用线程池在后台执行分块
            loop = asyncio.get_running_loop()
            chunks = await loop.run_in_executor(None, lambda: list(self.chunker.chunk(document)))
            
            self._total_chunks = len(chunks)
            
            # 产生中间状态更新
            progress = 0.3
            self._log_progress(progress, f"文档分块完成，共{self._total_chunks}个块，开始处理")
            yield self.status_tracker.to_dict()
            
            # 处理每个块并产生结果
            for i, chunk in enumerate(chunks):
                self._chunks_processed = i + 1
                
                # 每处理10个块更新一次状态
                if i % 10 == 0 or i == len(chunks) - 1:
                    progress = 0.3 + 0.6 * (i + 1) / self._total_chunks
                    self._log_progress(progress, f"已处理 {i+1}/{self._total_chunks} 个块")
                    yield self.status_tracker.to_dict()
                
                # 序列化块并产生结果
                chunk_text = self.chunker.serialize(chunk)
                chunk_metadata = {}
                if hasattr(chunk, 'meta') and chunk.meta:
                    # 尝试转换元数据为字典
                    try:
                        if hasattr(chunk.meta, 'model_dump'):
                            chunk_metadata = chunk.meta.model_dump()
                        elif hasattr(chunk.meta, 'dict'):
                            # 向后兼容，dict 方法已弃用，但仍然支持旧版本
                            chunk_metadata = chunk.meta.dict()
                        elif hasattr(chunk.meta, 'to_dict'):
                            chunk_metadata = chunk.meta.to_dict()
                        elif hasattr(chunk.meta, '__dict__'):
                            chunk_metadata = vars(chunk.meta)
                    except:
                        chunk_metadata = {"warning": "无法序列化块元数据"}
                
                yield {
                    "type": "chunk",
                    "index": i,
                    "content": chunk_text,
                    "metadata": chunk_metadata
                }
            
            # 完成
            self._log_progress(1.0, f"文档分块处理完成，共{self._total_chunks}个块")
            yield self.status_tracker.to_dict()
            
        except Exception as e:
            error_msg = f"文档分块过程中出现异常: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.status_tracker.update(
                stage=DocumentProcessStage.ERROR,
                progress=0.0,
                message=error_msg,
                error=str(e)
            )
            yield self.status_tracker.to_dict()
        finally:
            # 确保停止监控
            self.stop_monitoring() 