import os

def confirm_filepath(path):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)

    return path

def save_markdown(self, filepath: str, txt: str):
    """
    保存文本到文件。
    """

    if filepath and txt:
        confirm_filepath(filepath)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(txt)
