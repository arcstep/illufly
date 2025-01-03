import os
import platform

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
        # 文件夹配置
        "ILLUFLY_TEMP_DIR": FIXED_TEMP_DIR,
        "ILLUFLY_CONFIG_STORE_DIR": "__USERS__",
        "ILLUFLY_DOCS": "__DOCS__", # 从这个目录自动加载 RAG 资料，为避免误将不必要的资料做 RAG，因此需要设置为 __DOCS__
        "ILLUFLY_RESOURCE": "./", # 根据这个媒体文件夹上传文件，因此需要设置为当前目录
        "ILLUFLY_LOCAL_FILE_MEMORY": os.path.join(FIXED_TEMP_DIR, "LOCAL_FILE_MEMORY"), # LocalFileMemory 记忆存储目录
        "ILLUFLY_LOCAL_FILE_EVENTS": os.path.join(FIXED_TEMP_DIR, "LOCAL_FILE_EVENTS"), # LocalFileEvents 事件存储目录
        "ILLUFLY_CHAT_LEARN": os.path.join(FIXED_TEMP_DIR, "CHART_LEARN"), # ChatLearn 自我进化经验的存储目录
        "ILLUFLY_IDENT": os.path.join(FIXED_TEMP_DIR, "IDENT"), # 问题转换、意图识别的经验存储目录
        "ILLUFLY_CACHE_EMBEDDINGS": os.path.join(FIXED_TEMP_DIR, "CACHE_EMBEDDINGS"), # 缓存 Embeddings 存储目录
        "ILLUFLY_UPLOAD_CACHE": os.path.join(FIXED_TEMP_DIR, "UPLOAD_CACHE"), # 上传缓存目录
        "FASTAPI_TOKEN_WHITELIST": os.path.join(FIXED_TEMP_DIR, "AUTH", "whitelist.json"),

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

        # HTTP
        "HTTP_CHECK_RESULT_SECONDS": 2,

        # DashScope
        "DASHSCOPE_BASE_URL": "https://dashscope.aliyuncs.com/api/v1",
        # Zhipu
        "ZHIPUAI_API_TOOLS_BASE_URL": "https://open.bigmodel.cn/api/paas/v4/tools",

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
        "LOG_LEVEL": "INFO",
        "LOG_DIR": os.path.join(FIXED_TEMP_DIR, "__LOGS__"),
        "LOG_FILE_MAX_BYTES": 10 * 1024 * 1024,
        "LOG_FILE_BACKUP_COUNT": 10,
        "LOG_FORMAT": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "LOG_DATE_FORMAT": "%Y-%m-%d %H:%M:%S",
        "LOG_ENCODING": "utf-8",
        "LOG_MIN_FREE_SPACE": 100 * 1024 * 1024,

        # JiaoziCache
        "JIAOZI_BTREE_LRU_MAX_CACHE_SIZE": 1000,
        "JIAOZI_INDEX_FIELD_MAX_TAGS": 20,
        "JIAOZI_CACHE_STORE_DIR": os.path.join(FIXED_TEMP_DIR, "JIAOZI_CACHE"),  # 存储根目录
        "JIAOZI_CACHE_READ_SIZE": 1000,      # 读缓存大小
        "JIAOZI_CACHE_WRITE_SIZE": 1000,     # 写缓冲大小
        "JIAOZI_CACHE_FLUSH_INTERVAL": 60,   # 刷新间隔（秒）
        "JIAOZI_CACHE_FLUSH_THRESHOLD": 1000, # 刷新阈值

        # RocksDB数据库配置
        "ROCKSDB_BASE_DIR": os.path.join(FIXED_TEMP_DIR, "__ROCKSDB_STORE__"),  # 数据库根目录
        
        # 全局配置 - 内存相关
        "ROCKSDB_BLOCK_CACHE_SIZE": 512,      # Block缓存大小(MB)，建议为可用内存的30%
        "ROCKSDB_ROW_CACHE_SIZE": 128,        # 行缓存大小(MB)，建议为block cache的1/4
        
        # 全局配置 - 写入相关
        "ROCKSDB_WRITE_BUFFER_SIZE": 64,      # 单个memtable大小(MB)
        "ROCKSDB_MAX_WRITE_BUFFER_NUMBER": 4, # 最大memtable数量
        "ROCKSDB_MIN_WRITE_BUFFER_NUMBER": 2, # 最小memtable数量
        "ROCKSDB_LEVEL0_FILE_NUM_COMPACTION_TRIGGER": 4,  # L0文件数量触发合并阈值
        
        # 全局配置 - 性能优化
        "ROCKSDB_COMPRESSION": "lz4",         # 压缩算法(none/snappy/lz4/zstd)
        "ROCKSDB_BLOOM_BITS": 10,            # 布隆过滤器位数(8-16)
        "ROCKSDB_MAX_BACKGROUND_JOBS": 4,     # 后台任务线程数
        "ROCKSDB_ENABLE_PIPELINED_WRITE": True,  # 启用流水线写入
        
        # 默认列族配置
        "ROCKSDB_DEFAULT_CF_WRITE_BUFFER_SIZE": 32,  # 默认列族memtable大小(MB)
        "ROCKSDB_DEFAULT_CF_MAX_WRITE_BUFFER_NUMBER": 3,  # 默认列族最大memtable数量
        "ROCKSDB_DEFAULT_CF_COMPRESSION": "lz4",  # 默认列族压缩算法
    }
    if key:
        if key not in default_values:
            raise ValueError(f"Environ Value [{key}] Not Exist !!!")
        else:
            return os.getenv(key) or default_values[key]
    else:
        return default_values

def get_ascii_color_code(color_name: str):
    """
    获取 ASCII 颜色代码。
    """
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
