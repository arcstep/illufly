import os

def load_markdown(filename: str=None):
    """
    从文件加载文本。
    """

    txt = None
    if filename:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                txt = f.read()
    return txt
