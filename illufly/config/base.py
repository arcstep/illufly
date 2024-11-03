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
        "ILLUFLY_DOCS": "__DOCS__", # 从这个目录自动加载 RAG 资料，为避免误将不必要的资料做 RAG，因此需要设置为 __DOCS__
        "ILLUFLY_RESOURCE": "./", # 根据这个媒体文件夹上传文件，因此需要设置为当前目录
        "ILLUFLY_LOCAL_FILE_MEMORY": os.path.join(FIXED_TEMP_DIR, "LOCAL_FILE_MEMORY"), # LocalFileMemory 记忆存储目录
        "ILLUFLY_CHAT_LEARN": os.path.join(FIXED_TEMP_DIR, "CHART_LEARN"), # ChatLearn 自我进化经验的存储目录
        "ILLUFLY_IDENT": os.path.join(FIXED_TEMP_DIR, "IDENT"), # 问题转换、意图识别的经验存储目录
        "ILLUFLY_CACHE_EMBEDDINGS": os.path.join(FIXED_TEMP_DIR, "CACHE_EMBEDDINGS"), # 缓存 Embeddings 存储目录
        "ILLUFLY_UPLOAD_CACHE": os.path.join(FIXED_TEMP_DIR, "UPLOAD_CACHE"), # 上传缓存目录

        # 提示语
        "ILLUFLY_PROMPT_TEMPLATE_LOCAL_FOLDER": "__PROMPTS__",
        "ILLUFLY_FINAL_ANSWER_PROMPT": "**最终答案**",

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
        "ZHIPUAI_API_TOOLS_BASE_URL": "https://open.bigmodel.cn/api/paas/v4/tools"
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
