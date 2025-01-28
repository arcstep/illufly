import os
import platform
import tempfile

def get_env(key: str=None):
    """
    获取环境变量，如果没有设置就根据默认值清单返回默认值。
    """
    # 根据操作系统设置固定的临时目录
    if platform.system() == "Windows":
        FIXED_TEMP_DIR = os.path.join(os.getenv('TEMP'), "__ILLUFLY__")
    elif platform.system() == "Darwin":  # macOS
        FIXED_TEMP_DIR = os.path.join(os.getenv('TMPDIR', '/tmp'), "__ILLUFLY__")
    else:  # Linux and other Unix-like systems
        FIXED_TEMP_DIR = os.path.join('/tmp', "__ILLUFLY__")

    default_values = {
        # 缓存目录
        "ILLUFLY_CACHE_ROOT": FIXED_TEMP_DIR, # 缓存调用结果存储目录
        "ILLUFLY_CACHE_CALL": os.path.join(FIXED_TEMP_DIR, "CACHE_CALL"), # 缓存调用结果存储目录
        "ILLUFLY_ROCKSDB_TEMP": tempfile.mkdtemp(prefix="ILLUFLY_ROCKSDB_"), # RocksDB临时存储目录

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
        "HASH_METHOD": "pbkdf2_sha256",
        "FASTAPI_SECRET_KEY": "MY-SECRET-KEY",
        "FASTAPI_ALGORITHM": "HS256",
        "REFRESH_TOKEN_EXPIRE_DAYS": 30,
        "ACCESS_TOKEN_EXPIRE_MINUTES": 15,

        # Logging
        "LOG_LEVEL": "WARNING",
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
