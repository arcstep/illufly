import re
from typing import List, Union, Any
from langchain_core.documents import Document

def raise_not_install(packages):
    print(f"please install package: '{packages}' with pip or poetry")
    # auto install package
    # subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])

def raise_not_supply_all(info: str, *args):
    if all(arg is None for arg in args):
        raise ValueError(info)

def extract_text(resp_md: str, start_marker: str=None, end_marker: str=None):
    """
    如果指定开始和结束的标记，就提取标记中间的文本。
    """
    if start_marker and end_marker:
        start_index = resp_md.find(start_marker)
        end_index = resp_md.rfind(end_marker)

        if start_index != -1 and end_index != -1 and start_index < end_index:
            start_index += len(start_marker)
            return resp_md[start_index:end_index].strip()

    return resp_md

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