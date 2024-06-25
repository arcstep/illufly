import os
from .utils import color_code

def get_folder_root():
    return get_default_env("TEXTLONG_ROOT")

def get_folder_prompts():
    return get_default_env("TEXTLONG_PROMPTS")

def get_folder_logs():
    return get_default_env("TEXTLONG_LOGS")

def get_project_config_file():
    return get_default_env("TEXTLONG_CONFIG_FILE")

def get_project_script_file():
    return get_default_env("TEXTLONG_SCRIPT_FILE")

def get_folder_share():
    return get_default_env("TEXTLONG_SHARE")

def get_folder_history():
    return get_default_env("TEXTLONG_MEMORY_HISTORY")

def get_folder_qa():
    return get_default_env("TEXTLONG_QA")

def get_folder_docs():
    return get_default_env("TEXTLONG_DOCS")

def get_cache_embeddings():
    return get_default_env("TEXTLONG_CACHE_EMBEDDINGS")

def get_default_session():
    return get_default_env("TEXTLONG_DEFAULT_SESSION")

def get_default_user():
    return get_default_env("TEXTLONG_DEFAULT_USER")

def get_folder_public():
    return get_default_env("TEXTLONG_PUBLIC")

def get_text_color():
    return color_code(get_default_env("TEXTLONG_COLOR_TEXT"))

def get_info_color():
    return color_code(get_default_env("TEXTLONG_COLOR_INFO"))

def get_chunk_color():
    return color_code(get_default_env("TEXTLONG_COLOR_CHUNK"))

def get_warn_color():
    return color_code(get_default_env("TEXTLONG_COLOR_WARN"))



def get_default_env(key: str=None):
    """
    环境变量的默认值。
    """
    default_values = {
        # 根文件夹配置
        "TEXTLONG_ROOT": "",

        # 提示语文件夹
        "TEXTLONG_PROMPTS": "__PROMPTS__",

        # 项目文件夹
        "TEXTLONG_LOGS": "__LOG__",
        "TEXTLONG_SHARE": "__SHARE__",
        "TEXTLONG_DOCS": "__DOCS__",
        "TEXTLONG_QA": "__QA__",
        
        # 提示语缓存
        "TEXTLONG_CACHE_EMBEDDINGS": "__CACHE_EMBEDDINGS__",

        # 文档切分
        "TEXTLONG_DOC_CHUNK_SIZE": 2000,
        "TEXTLONG_DOC_CHUNK_OVERLAP": 300,

        # 项目文件
        "TEXTLONG_CONFIG_FILE": "project_config.yml",
        "TEXTLONG_SCRIPT_FILE": "project_script.yml",

        # 对话历史
        "TEXTLONG_MEMORY_HISTORY": "__MEMORY_HISTORY__",

        # 用户个人文件夹
        "TEXTLONG_DEFAULT_SESSION": "default",
        "TEXTLONG_DEFAULT_USER": "default_user",

        # 用户共享位置
        "TEXTLONG_PUBLIC": "",

        # 扩写标签
        "TEXTLONG_OUTLINE_START": "<OUTLINE>",
        "TEXTLONG_OUTLINE_END": "</OUTLINE>",
        "TEXTLONG_MORE_OUTLINE_START": "<MORE-OUTLINE>",
        "TEXTLONG_MORE_OUTLINE_END": "</MORE-OUTLINE>",

        # 上下文长度
        "TEXTLONG_DOC_PREV_K": 1000,
        "TEXTLONG_DOC_NEXT_K": 300,
        
        # 颜色
        "TEXTLONG_COLOR_INFO": "蓝色",
        "TEXTLONG_COLOR_TEXT": "黄色",
        "TEXTLONG_COLOR_WARN": "红色",
        "TEXTLONG_COLOR_CHUNK": "绿色",
        "TEXTLONG_COLOR_FINAL": "青色",
    }
    if key:
        if key not in default_values:
            raise ValueError(f"Environ Value [{key}] Not Exist !!!")
        else:
            return os.getenv(key) or default_values[key]
    else:
        return default_values
