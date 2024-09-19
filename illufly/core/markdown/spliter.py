from typing import Union, List
from .base import Markdown

def split_markdown(content: Union[str, Markdown], chunk_size: int=None, chunk_overlap: int=None) -> List[str]:
    """
    按照指定规则分割Markdown文档。

    :param chunk_size: 每个块的大小
    :param chunk_overlap: 每个块的覆盖大小
    :return: 分割后的文本块列表
    """
    chunk_size = chunk_size or 1024
    chunk_overlap = chunk_overlap or 20

    if isinstance(content, Markdown):
        text = content.text
    elif isinstance(content, str):
        text = content
    else:
        raise ValueError("Invalid content type. Expected Markdown or str.")

    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunks.append(text[start:end])
        start += chunk_size - chunk_overlap

    return chunks
