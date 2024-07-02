import os

def get_folder_root():
    return get_env("TEXTLONG_ROOT")

def get_env(key: str=None):
    """
    环境变量的默认值。
    """
    default_values = {
        # 根文件夹配置
        "TEXTLONG_ROOT": "./",

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
        "TEXTLONG_DEFAULT_OUTPUT": "output.md",
        "TEXTLONG_PROJECT_LIST": "project_list.yml",
        "TEXTLONG_CONFIG_FILE": "project_config.yml",
        "TEXTLONG_SCRIPT_FILE": "project_script.yml",

        # 对话历史
        "TEXTLONG_MEMORY_HISTORY": "__MEMORY_HISTORY__",

        # 用户个人文件夹
        "TEXTLONG_DEFAULT_SESSION": "default",
        "TEXTLONG_DEFAULT_USER": "default_user",

        # 用户共享位置
        "TEXTLONG_PUBLIC": "./",

        # 扩写标签
        "TEXTLONG_MARKDOWN_START": "```",
        "TEXTLONG_MARKDOWN_END": "```",
        "TEXTLONG_OUTLINE_START": "<OUTLINE>",
        "TEXTLONG_OUTLINE_END": "</OUTLINE>",
        "TEXTLONG_MORE_OUTLINE_START": "<MORE-OUTLINE>",
        "TEXTLONG_MORE_OUTLINE_END": "</MORE-OUTLINE>",

        # 上下文长度
        "TEXTLONG_DOC_PREV_K": 1000,
        "TEXTLONG_DOC_NEXT_K": 300,
        
        # 颜色
        "TEXTLONG_COLOR_DEFAULT": "黑色",
        "TEXTLONG_COLOR_INFO": "蓝色",
        "TEXTLONG_COLOR_TEXT": "黄色",
        "TEXTLONG_COLOR_WARN": "红色",
        "TEXTLONG_COLOR_CHUNK": "绿色",
        "TEXTLONG_COLOR_FINAL": "青色",
        "TEXTLONG_COLOR_FRONT_MATTER": "品红",
        
        # 多线程配置
        "TEXTLONG_MAX_WORKERS": 4,
        
        # FastAPI
        "FASTAPI_SECRET_KEY": "Your-Secret-Key",
        "FASTAPI_ALGORITHM": "HS256",
        "FASTAPI_TOKEN_WHITELIST": "token_whitelist.json",
    }
    if key:
        if key not in default_values:
            raise ValueError(f"Environ Value [{key}] Not Exist !!!")
        else:
            return os.getenv(key) or default_values[key]
    else:
        return default_values

def color_code(color_name: str):
    colors = {
        "黑色": "\033[30m",
        "红色": "\033[31m",
        "绿色": "\033[32m",
        "黄色": "\033[33m",
        "蓝色": "\033[34m",
        "品红": "\033[35m",
        "青色": "\033[36m",
        "白色": "\033[37m",
        "重置": "\033[0m" 
    }
    return colors.get(color_name, '黑色')

