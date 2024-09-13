import re
import os
import json
import hashlib
from typing import List, Union, Dict, Any
from langchain_core.documents import Document
from .config import get_env


def raise_not_install(packages):
    print(f"please install package: '{packages}' with pip or poetry")
    # auto install package
    # subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])

def raise_not_supply_all(info: str, *args):
    if all(arg is None for arg in args):
        raise ValueError(info)

def extract_text(resp_md: str, start_marker: str=None, end_marker: str=None):
    """
    如果指定开始和结束的标记，就提取标记中间的文本，并移除标记所在的行。
    一旦文本出现Markdown标题（若干个#开头的行），之后的内容就都不要进行start_marker匹配。
    """
    if start_marker and end_marker:
        start_lines = resp_md.split('\n')
        # 查找第一个Markdown标题的索引
        markdown_title_index = next((i for i, line in enumerate(start_lines) if line.strip().startswith('#')), len(start_lines))
        
        # 在第一个Markdown标题之前查找start_marker
        start_index = next((i for i, line in enumerate(start_lines[:markdown_title_index]) if start_marker in line), None)
        end_index = next((i for i, line in enumerate(reversed(start_lines), 1) if end_marker in line), None)

        if start_index is not None and end_index is not None and start_index < len(start_lines) - end_index:
            return '\n'.join(start_lines[start_index+1:len(start_lines)-end_index]).strip()

    return resp_md

def hash_text(text):
    text_bytes = text.encode('utf-8')
    hash_object = hashlib.md5(text_bytes)
    return hash_object.hexdigest()

def clean_filename(filename: str):
    """
    先将除字母、数字、中文、下划线和短横线之外的字符替换为下划线;
    再将多个连续的下划线或短横线替换为单个下划线。
    """
    cleaned_filename = re.sub(r'[^\w\s-]', '_', filename)
    cleaned_filename = re.sub(r'[-_ ]+', '_', cleaned_filename)
    return cleaned_filename

def safety_path(path: str):
    return os.path.normpath(re.sub(r"\.\.+", ".", path)) if path else ''

def compress_text(text: str, start_limit: int=100, end_limit: int=100, delta: int=50) -> str:
    """
    压缩文本，如果文本长度超过指定限制，则只保留前后部分，并用省略号连接。
    """
    if not text:
        return ''

    if len(text) <= start_limit + end_limit + delta:
        # 如果文本长度小于或等于前后限制之和，则直接返回原文本
        return text
    else:
        # 否则，保留前后部分并用省略号连接
        return text[:start_limit] + f"\n...(省略{len(text)-start_limit-end_limit}字)\n" + text[-end_limit:]

def merge_json_blocks(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    merged_result = {}

    for block in blocks:
        for key, value in block.items():
            if key not in merged_result:
                merged_result[key] = value
            else:
                if isinstance(value, dict) and isinstance(merged_result[key], dict):
                    merged_result[key] = merge_json_blocks([merged_result[key], value])
                elif key not in ['type'] and isinstance(value, str) and isinstance(merged_result[key], str):
                    merged_result[key] += value
                elif value != merged_result[key]:
                    merged_result[key] = value

    return merged_result

def merge_blocks_by_index(blocks: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    index_groups = {}
    for block in blocks:
        index = block.get('index')
        if index is not None:
            if index not in index_groups:
                index_groups[index] = []
            index_groups[index].append(block)
    
    merged_results = {index: merge_json_blocks(group) for index, group in index_groups.items()}
    return merged_results
