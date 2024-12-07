import os
import fnmatch
import json
import re
from typing import List
from ...utils import count_tokens
from ..document import Document

class MarkMeta():
    """MarkMeta 专注于解析带有扩展标签的 Markdown 文本"""
    
    def __init__(self, chunk_size: int = 1024, chunk_overlap: int = 100):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def parse_text(self, text: str) -> List[Document]:
        """解析文本内容
        
        Args:
            text: 要解析的文本内容
            
        Returns:
            List[Document]: 解析后的文档列表
        """
        docs = self.split_with_meta(text)
        result = []
        
        for doc in docs:
            if count_tokens(doc.text) > self.chunk_size:
                chunks = self.split_text_recursive(doc.text, doc.meta.get('source', 'unknown'))
                result.extend(chunks)
            else:
                result.append(doc)
                
        return result

    def split_with_meta(self, text: str) -> List[Document]:
        """
        按照 @meta 标签切分文档，每个片段单元作为独立的 Document 元素，并提取元数据。
        """
        documents = []
        split_text = re.split(r'\s*<!--\s*@meta', "\n" + text)
        for segment in split_text:
            if segment.strip() == "":
                continue
            lines = segment.split("\n")
            meta_line = lines[0].strip().replace("<!--", "").replace("-->", "").strip()
            content = "\n".join(lines[1:]).strip()

            try:
                # 直接将 meta_line 作为 JSON 解析
                meta = json.loads(meta_line)
            except json.JSONDecodeError as e:
                meta = {"raw_meta": meta_line}

            doc = Document(text=content, meta=meta)
            documents.append(doc)
        return documents

    def split_text_recursive(self, text: str, source: str) -> List[Document]:
        """
        按照指定规则分割Markdown文档。

        :return: 分割后Document对象列表
        """
        def split_text(text: str) -> List[str]:
            return text.split('\n')

        def create_chunk(lines: List[str], chunk_index: int) -> Document:
            return Document(text='\n'.join(lines), meta={"source": f"{source}#{chunk_index}"})

        chunks = []

        if not isinstance(text, str):
            raise ValueError("split_markdown的参数 text 必须是字符串")

        if not text or text.strip() == "":
            return chunks

        lines = split_text(text)
        current_chunk = []
        current_length = 0

        chunk_index = 0
        for line in lines:
            line_length = count_tokens(line)
            if line_length > self.chunk_size:
                continue  # 忽略超过chunk_size的最小单位

            if current_length + line_length > self.chunk_size:
                docs = [d for (l, d) in current_chunk]
                chunks.append(create_chunk(docs, chunk_index))
                
                # 计算重叠部分
                overlap_length = 0
                overlap_chunk = []
                for l, d in reversed(current_chunk):
                    overlap_length += l
                    overlap_chunk.insert(0, d)
                    if overlap_length >= self.chunk_overlap or overlap_length >= self.chunk_size / 2:
                        break

                current_chunk = [(count_tokens(d), d) for d in overlap_chunk]
                current_length = sum(l for l, _ in current_chunk)
                continue

            current_chunk.append((line_length, line))
            current_length += line_length
        if current_chunk:
            docs = [d for l, d in current_chunk]
            chunks.append(create_chunk(docs, chunk_index))

        return chunks
