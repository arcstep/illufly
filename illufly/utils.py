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
    1、从一对标记中提取，比如 ```turtle 和 ``` 之间，返回提取结果到列表中。
    2、如果包含多对标记，就返回提取到的多个结果列表。
    3、允许内容中同时存在多种标记，比如内容有些包含 ```turtle 和 ``` 之间，有些包含在```json 和 ``` 之间，应不会干扰。
    
    注意：开始标记必须严格位于行首（不允许有前导空格）。结束标记可以在行内或行首。
    """
    if not text or text.strip() == "":
        return []
        
    if not marker:
        return [text]

    start_marker, end_marker = marker
    start_marker_lower = start_marker.lower()
    end_marker_lower = end_marker.lower()
    
    lines = text.split('\n')
    segments = []

    capture = False
    current_segment = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # 处理开始标记（必须严格在行首）
        if not capture and line.lower().startswith(start_marker_lower):
            capture = True
            content_after_marker = line[len(start_marker):]
            
            if include_markers:
                current_segment.append(line)
            else:
                current_segment.append(content_after_marker.strip())
            
            # 检查同一行中的结束标记
            if end_marker_lower in content_after_marker.lower():
                # 找到结束标记的位置
                end_pos = content_after_marker.lower().find(end_marker_lower)
                
                # 判断是否为真正的结束标记：如果后面没有更多内容或后面不再包含结束标记
                is_real_end = True
                rest_of_line = content_after_marker[end_pos + len(end_marker_lower):].lower()
                if end_marker_lower in rest_of_line:
                    is_real_end = False
                
                if is_real_end:
                    if not include_markers:
                        # 提取标记之间的内容
                        content = content_after_marker[:end_pos].strip()
                        current_segment[-1] = content
                    
                    segments.append('\n'.join(current_segment).strip())
                    current_segment = []
                    capture = False
        
        # 在捕获模式下处理结束标记
        elif capture:
            if line.lower().startswith(end_marker_lower) or end_marker_lower in line.lower():
                # 两种情况：1. 行首结束标记 2. 行内结束标记
                is_real_end = True
                
                if line.lower().startswith(end_marker_lower):
                    # 行首结束标记通常是真正的结束标记
                    if include_markers:
                        current_segment.append(line)
                else:
                    # 行内结束标记，需要判断是否真正的结束标记
                    end_pos = line.lower().find(end_marker_lower)
                    rest_of_line = line[end_pos + len(end_marker_lower):].lower()
                    
                    # 如果后面还有结束标记，当前不是真正的结束
                    if end_marker_lower in rest_of_line:
                        is_real_end = False
                        current_segment.append(line)
                    else:
                        if include_markers:
                            current_segment.append(line)
                        else:
                            current_segment.append(line[:end_pos + len(end_marker_lower)].strip())
                
                if is_real_end:
                    segments.append('\n'.join(current_segment).strip())
                    current_segment = []
                    capture = False
            else:
                # 正常捕获的行
                current_segment.append(line)
        
        i += 1
    
    # 处理未闭合的标记
    if capture and current_segment and not strict:
        segments.append('\n'.join(current_segment).strip())
    
    # 如果没有找到任何片段
    if not segments:
        return [] if strict or not text else [text]
    
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

def clean_filename(filename):
    """
    清理文件名，将其转换为安全的格式。
    
    Args:
        filename: 需要清理的文件名，可以是字符串或其他类型
        
    Returns:
        str: 清理后的文件名
    """
    if filename is None:
        return "none"
    
    # 确保转换为字符串
    filename = str(filename)
    
    # 清理文件名
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
