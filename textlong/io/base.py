from abc import ABC, abstractmethod
from typing import Callable

from ..config import get_env, color_code

import hashlib
from datetime import datetime


class TextBlock():
    def __init__(self, block_type: str, content: str, thread_id: str=None):
        self.content = str(content)
        self.block_type = block_type
        self.thread_id = thread_id
        self.created_at = datetime.now()

    def __str__(self):
        return self.content
    
    def __repr__(self):
        return f"TextBlock(block_type=<{self.block_type}>, content=<{self.content}>)"
        
    @property
    def text(self):
        return self.content
    
    @property
    def text_with_print_color(self):
        color_mapping = {
            'text': "TEXTLONG_COLOR_TEXT",
            'code': "TEXTLONG_COLOR_INFO",
            'tool_resp': "TEXTLONG_COLOR_INFO",
            'tool_resp_chunk': "TEXTLONG_COLOR_INFO",
            'tools_call': "TEXTLONG_COLOR_INFO",
            'tools_call_final': "TEXTLONG_COLOR_INFO",
            'info': "TEXTLONG_COLOR_INFO",
            'warn': "TEXTLONG_COLOR_WARN",
            'final': "TEXTLONG_COLOR_FINAL",
            'chunk': "TEXTLONG_COLOR_CHUNK",
            'front_matter': "TEXTLONG_COLOR_FRONT_MATTER",
            'END': "TEXTLONG_COLOR_INFO"
        }

        env_var_name = color_mapping.get(self.block_type, "TEXTLONG_COLOR_DEFAULT")
        color = get_env(env_var_name)
        return color_code(color) + self.content + "\033[0m"

def create_chk_block(output_text: str):
    """
    生成哈希值
    """
    # 移除前后空格以确保唯一性
    trimmed_output_text = output_text.strip()
    hash_object = hashlib.sha256(trimmed_output_text.encode())
    # 获取十六进制哈希值
    hash_hex = hash_object.hexdigest()
    # 转换为8位数字哈希值
    hash_code = int(hash_hex, 16) % (10 ** 8)

    tail = f'【{get_env("TEXTLONG_AIGC_INFO_DECLARE")}，{get_env("TEXTLONG_AIGC_INFO_CHK")} {hash_code}】'

    return TextBlock("END", tail)


class BaseLog(ABC):
    @abstractmethod
    def __call__(self, func: Callable, *args, **kwargs):
        pass

    def end(self):
        return None

