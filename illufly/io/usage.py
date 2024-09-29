import json
from typing import AsyncIterable, Union
import logging
import asyncio

from .block import EventBlock

def mask_sensitive_info(calling_info):
    """
    遮盖 calling_info 中的敏感信息。
    """
    if calling_info:
        if "input" in calling_info:
            for key in ["api_key", "base_url"]:
                if key in calling_info["input"] and calling_info["input"][key]:
                    value = calling_info["input"][key]
                    if len(value) > 12:
                        masked_length = len(value) - 12
                        calling_info["input"][key] = f"{value[:8]}{'*' * masked_length}{value[-4:]}"
    return calling_info

def usage(block, verbose: bool=False, **kwargs):
    """
    记录 Runnable 的账单。
    """
    if isinstance(block, EventBlock) and block.block_type == "usage":
        block.calling_info = mask_sensitive_info(block.calling_info)
        print(block.json)

async def async_usage(block, verbose: bool=False, **kwargs):
    """
    记录 Runnable 的账单。
    """
    if isinstance(block, EventBlock) and block.block_type == "usage":
        block.calling_info = mask_sensitive_info(block.calling_info)
        print(block.json)
    await asyncio.sleep(0)
