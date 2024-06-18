import os

_NODES_FOLDER_NAME = "__NODES__"
_TEMPLATES_FOLDER_NAME = "__TEMPLATES__"
_CONTENTS_FOLDER_NAME = "__CONTENTS__"
_PROMPTS_CHAT_FOLDER_NAME = "__PROMPTS__/{action}/CHAT_TEMPLATE"
_PROMPTS_STRING_FOLDER_NAME = "__PROMPTS__/{action}/STRING_TEMPLATE"
_HISTORY_FOLDER_NAME = "__HISTORY__"
_QA_FOLDER_NAME = "__QA__"
_DOCS_FOLDER_NAME = "__DOCS__"
_TEMP_FOLDER_NAME = "__TEMP__"

def get_default_session():
    """默认的用户名"""
    return os.getenv("TEXTLONG_DEFAULT_SESSION") or "default"

def get_default_user():
    """默认的用户名"""
    return os.getenv("TEXTLONG_DEFAULT_USER") or "default_user"

def get_default_public():
    """默认的公共资料目录"""
    return os.getenv("TEXTLONG_PUBLIC") or ""

def get_default_project_logs():
    """默认的项目日志目录"""
    return os.getenv("TEXTLONG_PROJECT_LOGS") or "__logs__"

def get_default_project_config():
    """默认的项目配置文件"""
    return os.getenv("TEXTLONG_PROJECT_CONFIG") or "project_config.yml"

def get_default_project_script():
    """默认的项目脚本文件"""
    return os.getenv("TEXTLONG_PROJECT_SCRIPT") or "project_script.yml"

def get_textlong_folder():
    """从环境变量中获得项目的存储目录"""
    return os.getenv("TEXTLONG_FOLDER") or ""

def get_default_html_share():
    """默认的网页分享目录"""
    return os.getenv("TEXTLONG_DEFAULT_HTML_SHARE") or "html-share"
