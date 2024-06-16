import os
from ..writing.documents import MarkdownDocuments

def load_markdown(file_path: str=None) -> MarkdownDocuments:
    """
    从文件加载文本。
    """

    txt = None
    if file_path:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                txt = f.read()
    return MarkdownDocuments(txt)
