from .block import TextBlock
from ..config import get_env

import hashlib

def chk_tail(output_text: str):
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

    yield TextBlock("END", tail)
