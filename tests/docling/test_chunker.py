"""文档分块器测试模块

测试文档分块功能
"""

import pytest
from illufly.docling import (
    ChunkingStrategy,
    SimpleTextChunker,
    DocumentChunker,
    Chunk
)

@pytest.fixture
def simple_chunker():
    """创建简单文本分块器"""
    return SimpleTextChunker(chunk_size=100, overlap=20)

@pytest.fixture
def document_chunker(simple_chunker):
    """创建文档分块器"""
    return DocumentChunker(strategy=simple_chunker)

def test_simple_chunker_initialization(simple_chunker):
    """测试简单分块器初始化"""
    assert simple_chunker.chunk_size == 100
    assert simple_chunker.overlap == 20

def test_simple_chunker_small_text(simple_chunker):
    """测试小文本分块"""
    text = "这是一个短文本。"
    metadata = {"source": "test"}
    
    chunks = simple_chunker.chunk(text, metadata)
    
    assert len(chunks) == 1
    assert chunks[0].content == text
    assert chunks[0].metadata == metadata
    assert chunks[0].start_index == 0
    assert chunks[0].end_index == len(text)

def test_simple_chunker_large_text(simple_chunker):
    """测试大文本分块"""
    # 创建长文本
    text = "这是一个测试文本。" * 20
    metadata = {"source": "test"}
    
    chunks = simple_chunker.chunk(text, metadata)
    
    # 验证分块数量
    assert len(chunks) > 1
    
    # 验证每个分块
    for i, chunk in enumerate(chunks):
        assert len(chunk.content) <= simple_chunker.chunk_size
        assert chunk.metadata == metadata
        
        # 验证重叠
        if i > 0:
            prev_chunk = chunks[i-1]
            overlap = prev_chunk.end_index - chunk.start_index
            assert overlap == simple_chunker.overlap

def test_simple_chunker_sentence_boundary(simple_chunker):
    """测试句子边界分块"""
    text = "第一句话。第二句话。第三句话。第四句话。第五句话。"
    metadata = {"source": "test"}
    
    chunks = simple_chunker.chunk(text, metadata)
    
    # 验证分块在句子边界
    for chunk in chunks:
        assert chunk.content.endswith("。") or chunk.content == text

def test_document_chunker_initialization(document_chunker):
    """测试文档分块器初始化"""
    assert isinstance(document_chunker.strategy, SimpleTextChunker)
    assert document_chunker.strategy.chunk_size == 100
    assert document_chunker.strategy.overlap == 20

def test_document_chunker_chunking(document_chunker):
    """测试文档分块"""
    text = "这是一个测试文档。" * 10
    metadata = {"title": "测试文档"}
    
    chunks = document_chunker.chunk_document(text, metadata)
    
    assert len(chunks) > 1
    for chunk in chunks:
        assert isinstance(chunk, Chunk)
        assert chunk.metadata == metadata
        assert len(chunk.content) <= 100

def test_document_chunker_empty_text(document_chunker):
    """测试空文本分块"""
    text = ""
    metadata = {"title": "空文档"}
    
    chunks = document_chunker.chunk_document(text, metadata)
    
    assert len(chunks) == 1
    assert chunks[0].content == ""
    assert chunks[0].metadata == metadata
    assert chunks[0].start_index == 0
    assert chunks[0].end_index == 0

def test_document_chunker_metadata_preservation(document_chunker):
    """测试元数据保留"""
    text = "测试文本"
    metadata = {
        "title": "测试文档",
        "author": "测试作者",
        "date": "2024-01-01"
    }
    
    chunks = document_chunker.chunk_document(text, metadata)
    
    for chunk in chunks:
        assert chunk.metadata == metadata 