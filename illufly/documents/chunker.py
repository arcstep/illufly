from typing import List, Dict, Any, Optional
import logging
import re

logger = logging.getLogger(__name__)

class Chunker:
    """文档切片器基类"""
    
    def __init__(self, max_chunk_size: int = 1000, overlap: int = 100):
        """初始化切片器
        
        Args:
            max_chunk_size: 每个切片的最大字符数
            overlap: 相邻切片之间的重叠字符数
        """
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap
    
    async def chunk_document(self, content: str, metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """将文档内容切分为多个切片
        
        Args:
            content: 文档内容 (通常是markdown格式)
            metadata: 文档元数据
            
        Returns:
            List[Dict[str, Any]]: 切片列表，每个切片是一个字典，包含文本内容和元数据
        """
        raise NotImplementedError("子类必须实现此方法")

class MarkdownChunker(Chunker):
    """基于Markdown结构的文档切片器"""
    
    async def chunk_document(self, content: str, metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """将Markdown内容切分为多个有意义的切片
        
        切片策略:
        1. 尝试按照标题分割
        2. 如果切片太大，进一步按照段落分割
        3. 确保每个切片大小不超过max_chunk_size
        
        Args:
            content: Markdown文本内容
            metadata: 文档元数据
            
        Returns:
            List[Dict[str, Any]]: 切片列表
        """
        if not content:
            return []
            
        # 根据标题分割文档
        chunks = []
        
        # 使用正则表达式匹配Markdown标题
        headers = re.finditer(r'^(#{1,6})\s+(.+)$', content, re.MULTILINE)
        
        last_pos = 0
        current_title = "文档开头"
        
        # 遍历所有标题，按标题分割
        for match in headers:
            header_pos = match.start()
            header_level = len(match.group(1))
            header_text = match.group(2)
            
            # 如果不是文档的开头，将上一个标题到当前标题之间的内容作为一个切片
            if last_pos < header_pos:
                section_content = content[last_pos:header_pos].strip()
                if section_content:
                    # 检查切片大小，如果超过限制则进一步分割
                    self._add_section_chunks(chunks, section_content, current_title, metadata)
            
            # 更新当前标题和位置
            current_title = header_text
            last_pos = header_pos
        
        # 添加最后一个部分
        if last_pos < len(content):
            section_content = content[last_pos:].strip()
            if section_content:
                self._add_section_chunks(chunks, section_content, current_title, metadata)
        
        # 如果没有找到任何切片（没有标题结构），就按段落切分整个文档
        if not chunks:
            self._add_section_chunks(chunks, content, "文档内容", metadata)
            
        # 添加元数据
        for i, chunk in enumerate(chunks):
            chunk_metadata = {}
            if metadata:
                chunk_metadata.update(metadata)
            
            chunk_metadata.update({
                "index": i,
                "total_chunks": len(chunks),
                "next_index": i + 1 if i < len(chunks) - 1 else None,
                "prev_index": i - 1 if i > 0 else None
            })
            
            chunk["metadata"] = chunk_metadata
            
        return chunks
    
    def _add_section_chunks(self, chunks: List[Dict[str, Any]], content: str, title: str, metadata: Dict[str, Any] = None):
        """将内容按段落分割并添加到切片列表中"""
        if len(content) <= self.max_chunk_size:
            chunks.append({
                "content": content,
                "title": title
            })
            return
            
        # 按段落分割
        paragraphs = re.split(r'\n\s*\n', content)
        
        current_chunk = ""
        current_title = title
        
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
                
            # 如果添加当前段落会超过限制，先保存当前切片
            if len(current_chunk) + len(paragraph) + 2 > self.max_chunk_size and current_chunk:
                chunks.append({
                    "content": current_chunk,
                    "title": current_title
                })
                current_chunk = paragraph
            else:
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph
        
        # 添加最后一个切片
        if current_chunk:
            chunks.append({
                "content": current_chunk,
                "title": current_title
            })

# 工厂函数，根据文档类型选择合适的切片器
def get_chunker(doc_type: str = "markdown", **kwargs) -> Chunker:
    """获取适合特定文档类型的切片器
    
    Args:
        doc_type: 文档类型，如 "markdown", "text" 等
        **kwargs: 传递给切片器的参数
        
    Returns:
        Chunker: 切片器实例
    """
    if doc_type.lower() in ["markdown", "md"]:
        return MarkdownChunker(**kwargs)
    else:
        # 默认使用Markdown切片器
        logger.warning(f"未知的文档类型: {doc_type}，使用默认Markdown切片器")
        return MarkdownChunker(**kwargs)
