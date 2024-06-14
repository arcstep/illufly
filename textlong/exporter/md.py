import os

def confirm_filepath(path):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)

    return path

def save_markdown(filepath: str, txt: str):
    """
    保存文本到文件。
    """

    if filepath and txt:
        filepath = filepath if filepath.endswith(".md") else filepath + ".md"
        confirm_filepath(filepath)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(txt)

    return True
