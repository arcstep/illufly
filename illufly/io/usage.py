import json
from typing import AsyncIterable, Union
import logging
import asyncio

from .block import EventBlock

def mask_sensitive_info(data):
    """
    遮盖 data 中的敏感信息。
    """
    def mask_value(value):
        if len(value) > 12:
            masked_length = len(value) - 18
            return f"{value[:10]}{'*' * masked_length}{value[-8:]}"
        return value

    if data:
        for key in ["api_key", "base_url"]:
            if key in data and data[key]:
                data[key] = mask_value(data[key])
    return data

def usage(block, verbose: bool=False, **kwargs):
    """
    记录 Runnable 的账单。
    """
    if isinstance(block, EventBlock) and block.block_type == "usage":
        if block.calling_info and "input" in block.calling_info:
            block.calling_info["input"] = mask_sensitive_info(block.calling_info["input"])
        if block.runnable_info:
            block.runnable_info = mask_sensitive_info(block.runnable_info)
        print(block.json)

async def async_usage(block, verbose: bool=False, **kwargs):
    """
    记录 Runnable 的账单。
    """
    if isinstance(block, EventBlock) and block.block_type == "usage":
        if block.calling_info and "input" in block.calling_info:
            block.calling_info["input"] = mask_sensitive_info(block.calling_info["input"])
        if block.runnable_info:
            block.runnable_info = mask_sensitive_info(block.runnable_info)
        print(block.json)
    await asyncio.sleep(0)
