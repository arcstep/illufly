from typing import Any
import json
import hashlib
import numpy as np
import pandas as pd
import copy
from datetime import datetime

from ..config import get_env, color_code

class TextBlock():
    def __init__(self, block_type: str, content: str, thread_id: str=None):
        if content and not isinstance(content, str):
            raise ValueError("content 必须是字符串类型")
        self.content = content
        self.block_type = block_type
        self.thread_id = thread_id
        # self.created_at = datetime.now()

    def __str__(self):
        return self.content
    
    def __repr__(self):
        return f"TextBlock(block_type=<{self.block_type}>, content=<{self.content}>)"
    
    def json(self):
        return json.dumps({
            "block_type": self.block_type,
            "content": self.content,
            "thread_id": self.thread_id
        })

    @property
    def text(self):
        return self.content
    
    @property
    def text_with_print_color(self):
        color_mapping = {
            # 过程片段
            'chunk': "ILLUFLY_COLOR_CHUNK",
            'tools_call_chunk': "ILLUFLY_COLOR_CHUNK",
            'tool_resp_chunk': "ILLUFLY_COLOR_CHUNK",
            # 将片段累积后的输出
            'text_final': "ILLUFLY_COLOR_FINAL",
            'tools_call_final': "ILLUFLY_COLOR_FINAL",
            'tool_resp_final': "ILLUFLY_COLOR_FINAL",
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
        return color_code(color) + self.content + "\033[0m"

class EndBlock(TextBlock):
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
