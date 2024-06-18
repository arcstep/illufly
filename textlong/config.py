import os

def get_default_session():
    """默认的用户名"""
    return os.getenv("TEXTLONG_DEFAULT_SESSION") or "default"

def get_default_user():
    """默认的用户名"""
    return os.getenv("TEXTLONG_DEFAULT_USER") or "default_user"

def get_folder_public():
    """默认的公共资料目录"""
    return os.getenv("TEXTLONG_PUBLIC") or ""

def get_folder_prompts_chat(action: str):
    """默认的对话提示语模板目录"""
    return f'{get_folder_chat_prompts()}/{action}'

def get_folder_prompts_string(action: str):
    """默认的字符串提示语模板目录"""
    return f'{get_folder_string_prompts()}/{action}'

def get_folder_chat_prompts():
    return os.getenv("TEXTLONG_CHAT_PROMPTS") or "__CHAT_PROMPTS__"

def get_folder_string_prompts():
    """默认的项目提示语目录"""
    return os.getenv("TEXTLONG_STR_PROMPTS") or "__STR_PROMPTS__"

def get_folder_logs():
    """默认的项目日志目录"""
    return os.getenv("TEXTLONG_LOGS") or "__LOG__"

def get_project_config_file():
    """默认的项目配置文件"""
    return os.getenv("TEXTLONG_CONFIG_FILE") or "project_config.yml"

def get_project_script_file():
    """默认的项目脚本文件"""
    return os.getenv("TEXTLONG_SCRIPT_FILE") or "project_script.yml"

def get_folder_root():
    """从环境变量中获得项目的存储目录"""
    return os.getenv("TEXTLONG_ROOT") or ""

def get_folder_share():
    """默认的分享目录"""
    return os.getenv("TEXTLONG_SHARE") or "__SHARE__"

def get_folder_history():
    """默认的分享目录"""
    return os.getenv("TEXTLONG_MEMORY_HISTORY") or "__MEMORY_HISTORY__"

def get_folder_qa():
    return os.getenv("TEXTLONG_QA") or "__QA__"

def get_folder_docs():
    return os.getenv("TEXTLONG_DOCS") or "__DOCS__"
