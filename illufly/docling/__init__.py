"""Illufly's document processing and chunking module based on docling.

This module provides:
1. Document loading, recognition and processing capabilities
2. Chunking strategies for document splitting
3. Observable pipelines for monitoring document processing
"""

from .base import (
    DocumentProcessStage,
    DocumentProcessStatus,
    DocumentProcessor
)

from .observable import (
    ObservablePipeline,
    ObservablePdfPipeline
)

from .chunker import (
    ChunkingStrategy,
    DocumentChunker,
    SimpleTextChunker
)

from .loader import (
    DocumentLoader
)

__all__ = [
    'DocumentProcessStage',
    'DocumentProcessStatus',
    'DocumentProcessor',
    'ObservablePipeline',
    'ObservablePdfPipeline',
    'ChunkingStrategy',
    'DocumentChunker',
    'SimpleTextChunker',
    'DocumentLoader'
]
