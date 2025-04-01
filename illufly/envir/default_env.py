import os
import platform

def get_temp_dir(subdir: str=None):
    """获取临时目录"""
    subdir = subdir or ""
    if platform.system() == "Windows":
        return os.path.join(os.getenv('TEMP'), subdir)
    elif platform.system() == "Darwin":  # macOS
        return os.path.join(os.getenv('TMPDIR', '/tmp'), subdir)
    else:  # Linux and other Unix-like systems
        return os.path.join('/tmp', subdir)

def get_env(key: str=None):
    """
    获取环境变量，如果没有设置就根据默认值清单返回默认值。
    """
    # 根据操作系统设置固定的临时目录
    FIXED_TEMP_DIR = get_temp_dir("__ILLUFLY__")

    default_values = {
        # 支持的模型清单
        "ILLUFLY_VALID_MODELS": "gpt-4o-mini, gpt-4o",
        # 缓存目录
        "ILLUFLY_CACHE_LITELLM": os.path.join(FIXED_TEMP_DIR, "CACHE_LITELLM"),

        # 任务配置
        "ILLUFLY_L0_TASK_IMITATOR": "OPENAI",
        "ILLUFLY_L0_TASK_MODEL": "gpt-4o-mini",

        # 提示语
        "ILLUFLY_PROMPT_TEMPLATE_LOCAL_FOLDER": "__PROMPTS__",
        "ILLUFLY_FINAL_ANSWER_PROMPT": "最终答案",
        "ILLUFLY_FINAL_ANSWER_START": "<final_answer>",
        "ILLUFLY_FINAL_ANSWER_END": "</final_answer>",
        "ILLUFLY_CONTEXT_START": "<context>",
        "ILLUFLY_CONTEXT_END": "</context>",
        "ILLUFLY_KNOWLEDGE_START": "<knowledge>",
        "ILLUFLY_KNOWLEDGE_END": "</knowledge>",
        "ILLUFLY_OUTPUT_START": "```markdown",
        "ILLUFLY_OUTPUT_END": "```",

        # 结束语
        "ILLUFLY_AIGC_INFO_DECLARE": "内容由AI生成，其观点仅代表创作者个人立场",
        "ILLUFLY_AIGC_INFO_CHK": "可联系服务商查验校验码",

        # 扩写标签
        "ILLUFLY_OUTLINE_START": "<OUTLINE>",
        "ILLUFLY_OUTLINE_END": "</OUTLINE>",

        # log 颜色
        "ILLUFLY_COLOR_DEFAULT": "黑色",
        "ILLUFLY_COLOR_INFO": "蓝色",
        "ILLUFLY_COLOR_TEXT": "黄色",
        "ILLUFLY_COLOR_WARN": "红色",
        "ILLUFLY_COLOR_CHUNK": "绿色",
        "ILLUFLY_COLOR_FINAL": "青色",
        "ILLUFLY_COLOR_FRONT_MATTER": "品红",

        # Auth
        "FASTAPI_USERS_ADMIN_USERNAME": "admin",
        "FASTAPI_USERS_ADMIN_PASSWORD": "admin",
        "FASTAPI_USERS_ADMIN_EMAIL": "admin@illufly.com",
        "FASTAPI_SECRET_KEY": "MY-SECRET-KEY",
        "FASTAPI_ALGORITHM": "HS256",
        "FASTAPI_REFRESH_TOKEN_EXPIRE_DAYS": 30,
        "FASTAPI_ACCESS_TOKEN_EXPIRE_MINUTES": 5,

        # Logging
        "LOG_LEVEL": "INFO",
        "LOG_DIR": os.path.join(FIXED_TEMP_DIR, "__LOGS__"),
        "LOG_FILE_MAX_BYTES": 10 * 1024 * 1024,
        "LOG_FILE_BACKUP_COUNT": 10,
        "LOG_FORMAT": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "LOG_DATE_FORMAT": "%Y-%m-%d %H:%M:%S",
        "LOG_ENCODING": "utf-8",
        "LOG_MIN_FREE_SPACE": 100 * 1024 * 1024,
    }
    if key:
        if key not in default_values:
            raise ValueError(f"Environ Value [{key}] Not Exist !!!")
        else:
            return os.getenv(key) or default_values[key]
    else:
        return default_values
