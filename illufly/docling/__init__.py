"""
docling 模块

提供了文档处理、转换和分块的核心功能。
"""

# 直接导入所有组件以保持向后兼容性
from .schemas import DocumentProcessStage, DocumentProcessStatus
from .pipeline import ObservablePipelineWrapper
from .converter import ObservableConverter
from .base import process_document

__all__ = [
    'DocumentProcessStage',
    'DocumentProcessStatus',
    'ObservablePipelineWrapper',
    'ObservableConverter',
]
