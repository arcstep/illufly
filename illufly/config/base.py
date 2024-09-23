import os

def get_folder_root():
    return get_env("ILLUFLY_ROOT")

def get_env(key: str=None):
    """
    环境变量的默认值。
    """
    default_values = {
        # 文件夹配置
        "ILLUFLY_ROOT": "./",
        "ILLUFLY_DOCS": "__DOCS__",
        "ILLUFLY_PROMPTS": "__TEMPLATE_BASE__",

        # 项目文件夹
        "ILLUFLY_LOGS": "__LOG__",
        "ILLUFLY_SHARE": "__SHARE__",
        "ILLUFLY_QA": "__QA__",

        # 大模型
        "ILLUFLY_USER_MESSAGE_DEFAULT": "请开始",
        
        # 提示语缓存
        "ILLUFLY_CACHE_EMBEDDINGS": "__CACHE_EMBEDDINGS__",
        "ILLUFLY_EMBEDDINGS_BATCH_SIZE": 10240,

        # 文档切分
        "ILLUFLY_DOC_CHUNK_SIZE": 2000,
        "ILLUFLY_DOC_CHUNK_OVERLAP": 300,

        # 项目文件
        "ILLUFLY_DEFAULT_OUTPUT": "output.md",
        "ILLUFLY_PROJECT_LIST": "project_list.yml",
        "ILLUFLY_CONFIG_FILE": "project_config.yml",
        "ILLUFLY_SCRIPT_FILE": "project_script.yml",

        # 对话历史
        "ILLUFLY_MEMORY_HISTORY": "__MEMORY_HISTORY__",

        # 用户个人文件夹
        "ILLUFLY_DEFAULT_SESSION": "default",
        "ILLUFLY_DEFAULT_USER": "default_user",

        # 用户共享位置
        "ILLUFLY_PUBLIC": "./",

        # 扩写标签
        "ILLUFLY_MARKDOWN_START": "```",
        "ILLUFLY_MARKDOWN_END": "```",
        "ILLUFLY_OUTLINE_START": "<OUTLINE>",
        "ILLUFLY_OUTLINE_END": "</OUTLINE>",
        "ILLUFLY_MORE_OUTLINE_START": "<MORE-OUTLINE>",
        "ILLUFLY_MORE_OUTLINE_END": "</MORE-OUTLINE>",

        # 上下文长度
        "ILLUFLY_DOC_PREV_K": 1000,
        "ILLUFLY_DOC_NEXT_K": 300,
        
        # 颜色
        "ILLUFLY_COLOR_DEFAULT": "黑色",
        "ILLUFLY_COLOR_INFO": "蓝色",
        "ILLUFLY_COLOR_TEXT": "黄色",
        "ILLUFLY_COLOR_WARN": "红色",
        "ILLUFLY_COLOR_CHUNK": "绿色",
        "ILLUFLY_COLOR_FINAL": "青色",
        "ILLUFLY_COLOR_FRONT_MATTER": "品红",

        # 结束语
        "ILLUFLY_AIGC_INFO_DECLARE": "内容由AI生成，其观点仅代表创作者个人立场",
        "ILLUFLY_AIGC_INFO_CHK": "可联系服务商查验校验码",

        # 多线程配置
        "ILLUFLY_MAX_WORKERS": 4,
        
        # FastAPI
        "FASTAPI_SECRET_KEY": "Your-Secret-Key",
        "FASTAPI_ALGORITHM": "HS256",
        "FASTAPI_TOKEN_WHITELIST": "token_whitelist.json",

        # HTTP
        "HTTP_CHECK_RESULT_SECONDS": 2,

        # DashScope
        "DASHSCOPE_BASE_URL": "https://dashscope.aliyuncs.com/api/v1"
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

