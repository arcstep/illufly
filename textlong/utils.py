import re
from typing import List, Union
from langchain_core.documents import Document

def raise_not_install(packages):
    print(f"please install package: '{packages}' with pip or poetry")
    # auto install package
    # subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])

def raise_not_supply_all(info: str, *args):
    if all(arg is None for arg in args):
        raise ValueError(info)

def extract_text(resp_md: str):
    """
    如果存在>->>>和<<<-<结构，就提取第一个>->>>之后和最后一个<<<-<之前的文字
    """
    start_marker = '>->>>'
    end_marker = '<<<-<'
    
    start_index = resp_md.find(start_marker)
    end_index = resp_md.rfind(end_marker)
    
    if start_index != -1 and end_index != -1 and start_index < end_index:
        start_index += len(start_marker)
        return resp_md[start_index:end_index].strip()
    else:
        return resp_md