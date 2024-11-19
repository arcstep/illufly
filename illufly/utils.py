import re
import os
import json
import hashlib
import tiktoken
import time
import random
from typing import List, Union, Dict, Any, Tuple
from .config import get_env
import threading

def filter_kwargs(kwargs: Dict, allowed_params: Dict):
    """
    根据 allowed_params 过滤掉不支持的参数。
    """
    return {k: v for k, v in kwargs.items() if k in allowed_params}

def raise_invalid_params(kwargs: Dict, allowed_params: Dict):
    """
    根据 allowed_params 检查参数是否合法。
    """
    invalid_params = [k for k in kwargs.keys() if k not in allowed_params]
    if invalid_params:
        raise ValueError(f"invalid parameters: {invalid_params}")

def raise_not_install(packages):
    """
    如果指定的包未安装，则抛出错误。
    """
    print(f"please install package: '{packages}' with pip or poetry")
    # auto install package
    # subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])

def raise_not_supply_all(info: str, *args):
    """
    如果所有参数都为None，则抛出错误。
    """
    if all(arg is None for arg in args):
        raise ValueError(info)

def extract_segments(text: str, marker: Tuple[str, str], include_markers: bool = False, strict: bool = False) -> List[str]:
    """
    根据模式提取文本中符合条件的片段。
    mode='multiple'：提取每一对start_marker和end_marker之间的内容。
    mode='single'：提取第一个start_marker和最后一个end_marker之间的内容。
    """
    if not marker:
        return [text] if text else []

    start_marker, end_marker = marker
    lines = text.split('\n')
    segments = []

    capture = False
    current_segment = []
    for line in lines:
        stripped_line = line.strip().lower()
        if not capture and start_marker.lower() in stripped_line:
            capture = True
            if include_markers:
                current_segment.append(line)
                start_pos = stripped_line.index(start_marker.lower()) + len(start_marker)
            else:
                start_pos = line.lower().index(start_marker.lower()) + len(start_marker)
                current_segment.append(line[start_pos:].strip())
            # 检查 end_marker 是否在同一行
            if end_marker.lower() in stripped_line[start_pos:]:
                end_pos = line.lower().index(end_marker.lower(), start_pos)
                current_segment[-1] = line[start_pos:end_pos].strip()
                segments.append('\n'.join(current_segment).strip())
                capture = False
                current_segment = []  # 重置 current_segment
        elif capture and end_marker.lower() in stripped_line:
            if include_markers:
                current_segment.append(line)
            else:
                end_pos = line.lower().index(end_marker.lower())
                current_segment.append(line[:end_pos].strip())
            segments.append('\n'.join(current_segment).strip())
            capture = False
            current_segment = []  # 重置 current_segment
        elif capture:
            current_segment.append(line.strip())
    # 确保在捕获结束后清空 current_segment
    if capture:
        segments.append('\n'.join(current_segment).strip())
        capture = False
    
    if not strict and not segments:
        # 如果什么都没发现就返回原始输入
        return [text]

    return segments

def extract_text(resp_md: str, marker: Tuple[str, str], include_markers: bool=False, strict: bool=False):
    return "\n".join(extract_segments(resp_md, marker, include_markers=include_markers, strict=strict))

def extract_final_answer(text: str, final_answer_prompt: str="最终答案"):
    """
    提取文本中以 final_answer_prompt 开头的文本。
    """
    final_answer_lines = []
    capture = False

    # 预处理 final_answer_prompt，仅保留字母、中文、数字、下划线和横杠
    processed_prompt = re.sub(r'[^\w\u4e00-\u9fff-]', '', final_answer_prompt)

    for line in text.split('\n'):
        # 预处理行，仅保留字母、中文、数字、下划线和横杠
        processed_line = re.sub(r'[^\w\u4e00-\u9fff-]', '', line)
        if processed_line == processed_prompt:
            capture = True
            # 直接添加整行，而不是从 final_answer_prompt 的长度位置开始
            final_answer_lines.append(line.strip())
        elif capture:
            final_answer_lines.append(line)
    final_answer_text = '\n'.join(final_answer_lines).strip()

    return extract_text(final_answer_text, ("```markdown", "```")) if final_answer_text else ''

def hash_text(text):
    """
    计算文本的MD5哈希值。主要用于生成反向索引，便于缓存命中等。
    """
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
    """
    确保路径中不包含 .. ，防止通过路径注入获得系统中其他资源的路径。
    替换路径中的 .. 为 .，并返回安全过滤后的路径。
    """
    return os.path.normpath(re.sub(r"\.\.+", ".", path)) if path else ''

def minify_text(text: str, limit: int=100) -> str:
    """
    在长度限制下，仅保留文本的开头部份即可，一般用于调试信息。
    压缩文本，剔除左右两侧的空格和换行，仅保留第一个换行之前的文字，超出后limit后用省略号代替。
    """
    raw_len = len(text)
    if not text:
        return ''
    
    text = text.strip()
    minified_text = text[:limit].replace("\n", "<br>")
    if len(minified_text) < raw_len:
        minified_text += f'...'
    
    return minified_text

def compress_text(text: str, start_limit: int=100, end_limit: int=100, delta: int=50) -> str:
    """
    在长度限制下，保留尽量多的文本，一般用于提示语参考。
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

def merge_tool_calls(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    合并流式输出的JSON表示。
    """
    merged_results = []
    current_result = None

    for block in blocks:
        if current_result is None or (block.get('id') and block['id'] != current_result['id']):
            if current_result:
                merged_results.append(current_result)
            current_result = block.copy()
        else:
            for key, value in block.items():
                if isinstance(value, dict):
                    if key == 'function':
                        current_result[key] = merge_function_fields(current_result.get(key, {}), value)
                    else:
                        current_result[key] = merge_json_blocks([current_result.get(key, {}), value])
                elif isinstance(value, str):
                    if key in ['type'] and value:
                        if value != current_result.get(key, ''):
                            current_result[key] = value 
                    else:
                        current_result[key] = current_result.get(key, '') + value
                else:
                    current_result[key] = value

    if current_result:
        merged_results.append(current_result)

    return merged_results

def merge_json_blocks(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    merged_result = {}

    for block in blocks:
        for key, value in block.items():
            if key not in merged_result:
                merged_result[key] = value
            else:
                if isinstance(value, dict) and isinstance(merged_result[key], dict):
                    if key == 'function':
                        merged_result[key] = merge_function_fields(merged_result[key], value)
                    else:
                        merged_result[key] = merge_json_blocks([merged_result[key], value])
                elif value != merged_result[key]:
                    merged_result[key] = value

    return merged_result

def merge_function_fields(original: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    merged_function = original.copy()
    if 'name' in new:
        merged_function['name'] = original.get('name', '') + new['name']
    if 'arguments' in new:
        merged_function['arguments'] = original.get('arguments', '') + new['arguments']
    return merged_function

def merge_blocks_by_index(blocks: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    index_groups = {}
    for block in blocks:
        index = block.get('index')
        if index is not None:
            if index not in index_groups:
                index_groups[index] = []
            index_groups[index].append(block)
    
    merged_results = {index: merge_tool_calls(group) for index, group in index_groups.items()}
    return merged_results

def count_tokens(text: str):
    """
    计算文本的 token 数量。
    """
    return len(get_token_ids(text))

def get_token_ids(text: str, token_encoding: str=None, allowed_special: str=None, disallowed_special: str=None) -> List[int]:
    """
    获取文本的 token ID 列表。
    """
    encoding_model = tiktoken.get_encoding(token_encoding or 'cl100k_base')
    return encoding_model.encode(
        text,
        allowed_special = allowed_special or set(),
        disallowed_special = disallowed_special or "all",
    )

def escape_xml_tags(text, tags_to_escape=None):
    if tags_to_escape is None:
        tags_to_escape = ['tool_call', 'final_answer', 'sub_task', 'context', 'knowledge']
    
    def replace_tag(match):
        tag = match.group(0)
        return tag.replace("<", "&lt;").replace(">", "&gt;")
    
    # 构建正则表达式，仅匹配行首的需要转义的标签
    tags_pattern = '|'.join(tags_to_escape)
    regex_pattern = rf'^(</?({tags_pattern})>)|((</?({tags_pattern})>)$)'
    
    # 对每一行进行处理
    lines = text.splitlines()
    escaped_lines = [re.sub(regex_pattern, replace_tag, line) for line in lines]
    
    return '\n'.join(escaped_lines)

class IDGenerator:
    """
    ID 生成器。

    ID 的格式为：`YYYYMMDD-TIMESTAMP-NNNN-XXXX`
    其中，YYYYMMDD 表示日期，TIMESTAMP 表示当日秒数，XXXX 表示随机数，NNNN 表示计数。
    """
    def __init__(self, counter: int = 0):
        self.counter = counter
        self._lock = threading.Lock()

    def __iter__(self):
        return self

    def __next__(self):
        with self._lock:
            date_str = time.strftime("%Y%m%d")
            timestamp = str(int(time.time()))[-5:]
            random_number = f'{random.randint(0, 9999):04}'
            counter_str = f'{self.counter:04}'
            unique_id = f'{date_str}-{timestamp}-{counter_str}-{random_number}'
            self.counter = 0 if self.counter == 9999 else self.counter + 1
            return unique_id

def create_id_generator(counter: int = 0) -> IDGenerator:
    return IDGenerator(counter)
