import os

_NODES_FOLDER_NAME = "__NODES__"
_TEMPLATES_FOLDER_NAME = "__TEMPLATES__"
_CONTENTS_FOLDER_NAME = "__CONTENTS__"
_PROMPTS_FOLDER_NAME = "__PROMPTS__"
_HISTORY_FOLDER_NAME = "__HISTORY__"
_QA_FOLDER_NAME = "__QA__"
_DOCS_FOLDER_NAME = "__DOCS__"
_TEMP_FOLDER_NAME = "__TEMP__"

def get_textlong_folder():
    """从环境变量中获得项目的存储目录"""
    return os.getenv("TEXTLONG_FOLDER") or "textlong_data"

def get_textlong_doc(filename: str, folder_name: str = ""):
    return os.path.join(get_textlong_folder(), folder_name, filename)
