from typing import Callable
from ..config import get_env, color_code

import json
import hashlib
from datetime import datetime

class TextBlock():
    def __init__(self, block_type: str, content: str, thread_id: str=None):
        self.content = str(content)
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
            # markdown 配置头
            'front_matter': "ILLUFLY_COLOR_FRONT_MATTER",
            # 工具回调过程中产生的片段，这可能是工具执行过程中的碎片信息
            'tool_resp_chunk': "ILLUFLY_COLOR_CHUNK",
            # 工具回调最终结果，一般不是直接由片段合成
            'tool_resp_final': "ILLUFLY_COLOR_FINAL",
            # 大模型推理要求的工具片段文本
            'tools_call_chunk': "ILLUFLY_COLOR_CHUNK",
            # 大模型推理要求的工具最终结果
            'tools_call_final': "ILLUFLY_COLOR_FINAL",
            # 直接输出的文本
            'text': "ILLUFLY_COLOR_TEXT",
            # 大模型推理的中间结果片段文本
            'chunk': "ILLUFLY_COLOR_CHUNK",
            # 大模型推理的最终结果
            'text_final': "ILLUFLY_COLOR_FINAL",
            # 智能体节点
            'agent': "ILLUFLY_COLOR_INFO",
            # 提示信息
            'info': "ILLUFLY_COLOR_INFO",
            # 警告信息
            'warn': "ILLUFLY_COLOR_WARN",
            # 结束信息
            'END': "ILLUFLY_COLOR_INFO"
        }

        env_var_name = color_mapping.get(self.block_type, "ILLUFLY_COLOR_DEFAULT")
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

    tail = f'【{get_env("ILLUFLY_AIGC_INFO_DECLARE")}，{get_env("ILLUFLY_AIGC_INFO_CHK")} {hash_code}】'

    return TextBlock("END", tail)
