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
        "ILLUFLY_HISTORY": "__XP__/HISTORY",
        "ILLUFLY_FAQ": "__XP__/FAQ",
        "ILLUFLY_IDENT": "__XP__/IDENT",
        "ILLUFLY_DOCS": "__DOCS__",
        "ILLUFLY_PROMPT_TEMPLATE_LOCAL_FOLDER": "__PROMPTS__",
        "ILLUFLY_MEDIA": "__MEDIA__",
        "ILLUFLY_CACHE_EMBEDDINGS": "__CACHE_EMBEDDINGS__",
        "ILLUFLY_UPLOAD_CACHE_DIR": "__UPLOAD_CACHE__",

        # 提示词
        "ILLUFLY_FINAL_ANSWER_PROMPT": "**最终答案**",

        # 结束语
        "ILLUFLY_AIGC_INFO_DECLARE": "内容由AI生成，其观点仅代表创作者个人立场",
        "ILLUFLY_AIGC_INFO_CHK": "可联系服务商查验校验码",

        # 扩写标签
        "ILLUFLY_OUTLINE_START": "<OUTLINE>",
        "ILLUFLY_OUTLINE_END": "</OUTLINE>",

        # 颜色
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

