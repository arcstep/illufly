import json
import time
import asyncio

from typing import Callable, Iterable, Union, AsyncIterable
from .block import EventBlock, NewLineBlock

__CHUNK_BLOCK_TYPES__ = ["text", "chunk", "tool_resp_chunk"]
__NOT_PRINT_BLOCK_TYPES__ = ["final_text", "response"]
__ALLWAYS_PRINT_BLOCK_TYPES__ = ["final_tools_call", "agent", "faq", "warn", "error", "image_url"]

def process_block(block, verbose:bool):
    if isinstance(block, EventBlock):  
        if block.block_type == "new_line":
            print()
        elif block.block_type in __CHUNK_BLOCK_TYPES__:
            print(block.text_with_print_color, end="")
        else:
            if (verbose or block.block_type in __ALLWAYS_PRINT_BLOCK_TYPES__):
                print(f'[{block.block_type.upper()}] {block.text_with_print_color}')
    elif isinstance(block, str):
        print(block)
    else:
        raise ValueError(f"Unknown block type: {block}")

def log(block, verbose: bool=False, **kwargs):
    """
    打印流式日志。
    """
    if isinstance(block, EventBlock) and block.block_type in __NOT_PRINT_BLOCK_TYPES__:
        return
    process_block(block, verbose=verbose)

async def alog(block, verbose: bool=False, **kwargs):
    """
    打印流式日志。
    """
    if isinstance(block, EventBlock) and block.block_type in __NOT_PRINT_BLOCK_TYPES__:
        return
    process_block(block, verbose=verbose)
    await asyncio.sleep(0)

