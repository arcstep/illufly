import os

def get_folder_root():
    return get_default_env("TEXTLONG_ROOT")

def get_folder_prompts_chat(action: str):
    return f'{get_folder_chat_prompts()}/{action}'

def get_folder_prompts_string(action: str):
    return f'{get_folder_string_prompts()}/{action}'

def get_folder_chat_prompts():
    return get_default_env("TEXTLONG_CHAT_PROMPTS")

def get_folder_string_prompts():
    return get_default_env("TEXTLONG_STR_PROMPTS")

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

def get_default_session():
    return os.getenv("TEXTLONG_DEFAULT_SESSION") or "default"

def get_default_user():
    return os.getenv("TEXTLONG_DEFAULT_USER") or "default_user"

def get_folder_public():
    return os.getenv("TEXTLONG_PUBLIC") or ""

def get_default_env(key: str=None):
    """
    环境变量的默认值。
    """
    default_values = {
        # 根文件夹配置
        "TEXTLONG_ROOT": "",

        # 提示语文件夹
        "TEXTLONG_CHAT_PROMPTS": "__CHAT_PROMPTS__",
        "TEXTLONG_STR_PROMPTS": "__STR_PROMPTS__",

        # 项目文件夹
        "TEXTLONG_LOGS": "__LOG__",
        "TEXTLONG_SHARE": "__SHARE__",
        "TEXTLONG_DOCS": "__DOCS__",
        "TEXTLONG_QA": "__QA__",

        # 项目文件
        "TEXTLONG_CONFIG_FILE": "project_config.yml",
        "TEXTLONG_SCRIPT_FILE": "project_script.yml",

        # 对话历史
        "TEXTLONG_MEMORY_HISTORY": "__MEMORY_HISTORY__",

        # 用户个人文件夹
        "TEXTLONG_DEFAULT_SESSION": "default",
        "TEXTLONG_DEFAULT_USER": "default_user",

        # 公共用户
        "TEXTLONG_PUBLIC": "",
    }
    if key:
        if key not in default_values:
            raise ValueError(f"Environ Value [{key}] Not Exist !!!")
        else:
            return os.getenv(key) or default_values[key]
    else:
        return default_values