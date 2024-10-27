from typing import Any
import json
import hashlib
import numpy as np
import pandas as pd
import copy
from datetime import datetime

from ..config import get_env, get_ascii_color_code

class EventBlock():
    def __init__(
        self, 
        block_type: str, 
        content: Any, 
        created_at: datetime=None, 
        calling_info: dict=None,
        runnable_info: dict=None
    ):
        self.content = content
        self.block_type = block_type.lower()
        self.created_at = created_at or datetime.now()
        self.calling_info = calling_info or {}
        self.runnable_info = runnable_info or {}

    def __str__(self):
        return self.text
    
    def __repr__(self):
        return f"EventBlock(block_type=<{self.block_type}>, content=<{self.text}>)"
    
    @property
    def json(self):
        return json.dumps({
            "block_type": self.block_type,
            "content": self.text,
            "created_at": self.created_at.isoformat(),
            "calling_info": self.calling_info,
            "runnable_info": self.runnable_info,
        }, ensure_ascii=False)

    @property
    def text(self):
        """
        兼容多模态时返回图像、视频等情况
        """
        if isinstance(self.content, str):
            return self.content
        elif isinstance(self.content, list):
            items = []
            for item in self.content:
                if isinstance(item, dict) and "text" in item:
                    items.append(item["text"])
                else:
                    items.append(json.dumps(item, ensure_ascii=False))
            return ",".join(items)
        else:
            return str(self.content)
    
    @property
    def text_with_print_color(self):
        color_mapping = {
            # 过程片段
            'chunk': "ILLUFLY_COLOR_CHUNK",
            'tools_call_chunk': "ILLUFLY_COLOR_CHUNK",
            'tool_resp_chunk': "ILLUFLY_COLOR_CHUNK",
            # 将片段累积后的输出
            'final_text': "ILLUFLY_COLOR_FINAL",
            'final_tools_call': "ILLUFLY_COLOR_FINAL",
            'final_tool_resp': "ILLUFLY_COLOR_FINAL",
            # 直接输出的文本
            'text': "ILLUFLY_COLOR_TEXT",
            'image_url': "ILLUFLY_COLOR_TEXT",
            # 警告信息
            'warn': "ILLUFLY_COLOR_WARN",
            # 其他信息
            'unknown': "ILLUFLY_COLOR_INFO",
        }

        env_var_name = color_mapping.get(self.block_type, "ILLUFLY_COLOR_INFO")
        color = get_env(env_var_name)
        return get_ascii_color_code(color) + self.text + "\033[0m"

class ResponseBlock(EventBlock):
    """
    用于在使用生成器的函数之间传递返回值。
    """
    def __init__(self, resp: Any, *args, **kwargs):
        super().__init__("RESPONSE", *args, **kwargs)

class EndBlock(EventBlock):
    def __init__(self, output_text: str):
        tail_text = self.create_chk_block(output_text)
        super().__init__("END", tail_text)

    def create_chk_block(self, output_text: str):
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

        tail = f'【{get_env("ILLUFLY_AIGC_INFO_DECLARE")}，{get_env("ILLUFLY_AIGC_INFO_CHK")} {hash_code}】'

        return tail

class NewLineBlock(EventBlock):
    def __init__(self, *args, **kwargs):
        super().__init__("new_line", "", *args, **kwargs)

