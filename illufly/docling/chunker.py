"""文档分块模块

提供文档分块策略和实现，包括：
1. 分块策略接口
2. 简单文本分块器
3. 文档分块器
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import re

@dataclass
class Chunk:
    """文档分块"""
    content: str
    metadata: Dict[str, Any]
    start_index: int
    end_index: int

class ChunkingStrategy(ABC):
    """分块策略接口"""
    
    @abstractmethod
    def chunk(self, text: str, metadata: Dict[str, Any]) -> List[Chunk]:
        """将文本分块
        
        Args:
            text: 待分块的文本
            metadata: 元数据
            
        Returns:
            分块列表
        """
        pass

class SimpleTextChunker(ChunkingStrategy):
    """简单文本分块器"""
    
    def __init__(self, chunk_size: int = 1000, overlap: int = 200):
        """初始化简单文本分块器
        
        Args:
            chunk_size: 分块大小
            overlap: 重叠大小
        """
        self.chunk_size = chunk_size
        self.overlap = overlap
    
    def chunk(self, text: str, metadata: Dict[str, Any]) -> List[Chunk]:
        """将文本分块"""
        chunks = []
        text_length = len(text)
        
        if text_length <= self.chunk_size:
            chunks.append(Chunk(
                content=text,
                metadata=metadata,
                start_index=0,
                end_index=text_length
            ))
            return chunks
        
        start = 0
        while start < text_length:
            end = min(start + self.chunk_size, text_length)
            
            # 如果还没到文本末尾，尝试在句子边界处分割
            if end < text_length:
                # 查找最近的句子结束符
                sentence_end = max(
                    text.rfind('.', start, end),
                    text.rfind('。', start, end),
                    text.rfind('!', start, end),
                    text.rfind('！', start, end),
                    text.rfind('?', start, end),
                    text.rfind('？', start, end)
                )
                
                if sentence_end > start + self.chunk_size // 2:
                    end = sentence_end + 1
            
            chunks.append(Chunk(
                content=text[start:end],
                metadata=metadata,
                start_index=start,
                end_index=end
            ))
            
            # 更新起始位置，考虑重叠
            start = end - self.overlap
        
        return chunks

class DocumentChunker:
    """文档分块器"""
    
    def __init__(self, strategy: Optional[ChunkingStrategy] = None):
        """初始化文档分块器
        
        Args:
            strategy: 分块策略，默认为简单文本分块器
        """
        self.strategy = strategy or SimpleTextChunker()
    
    def chunk_document(self, text: str, metadata: Dict[str, Any]) -> List[Chunk]:
        """分块文档
        
        Args:
            text: 文档文本
            metadata: 文档元数据
            
        Returns:
            分块列表
        """
        return self.strategy.chunk(text, metadata) 