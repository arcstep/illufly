import json
import time

from typing import Callable, Iterable, Union, AsyncIterable
from .block import TextBlock
from ..core.agent.base import Runnable

__CHUNK_BLOCK_TYPES__ = ["chunk", "tool_resp_chunk"]
__NOT_PRINT_BLOCK_TYPES__ = ["text_final"]
__ALLWAYS_PRINT_BLOCK_TYPES__ = ["agent", "warn", "error", "image_url"]

def process_block(block, last_block_type, verbose:bool, start_time:float):
    elapsed_time = int(time.time() - start_time)
    if isinstance(block, TextBlock):        
        if block.block_type in __CHUNK_BLOCK_TYPES__:
            if last_block_type and last_block_type in __CHUNK_BLOCK_TYPES__ and last_block_type != block.block_type:
                print("\n")
            print(block.text_with_print_color, end="")
        else:
            if last_block_type in __CHUNK_BLOCK_TYPES__:
                print("\n")
            if (verbose or block.block_type in __ALLWAYS_PRINT_BLOCK_TYPES__):
                print(f'{elapsed_time:3d}s [{block.block_type.upper()}] {block.text_with_print_color}')
    elif isinstance(block, str):
        print(block)
    else:
        raise ValueError(f"Unknown block type: {block}")
    
    return block.block_type

def log(runnable: Runnable, *args, verbose: bool=False, **kwargs):
    """
    针对任何回调函数，只要符合规范的返回TextBlock对象的生成器，就可以使用这个函数来
    打印流式日志。

    返回值中，tools_call可以方便处理智能体的工具回调。
    """
    if not isinstance(runnable, Runnable):
        raise ValueError("call_obj 必须是 Runnable 实例")

    last_block_type = ""
    start_time = time.time()

    for block in runnable.call(*args, **kwargs):
        if isinstance(block, TextBlock) and block.block_type in __NOT_PRINT_BLOCK_TYPES__:
            continue
        last_block_type = process_block(block, last_block_type, verbose=verbose, start_time=start_time)
        
    if last_block_type in __CHUNK_BLOCK_TYPES__:
        print("\n")
    
    return runnable.output

async def alog(runnable: Runnable, *args, verbose: bool=False, **kwargs):
    """
    针对任何回调函数，只要符合规范的返回TextBlock对象的生成器，就可以使用这个函数来
    打印流式日志。

    返回值中，tools_call可以方便处理智能体的工具回调。
    """

    last_block_type = ""
    start_time = time.time()

    resp = runnable.async_call(*args, **kwargs)
    async for block in resp:
        if isinstance(block, TextBlock) and block.block_type in __NOT_PRINT_BLOCK_TYPES__:
            continue
        last_block_type = process_block(block, last_block_type, verbose=verbose, start_time=start_time)
        
    if last_block_type in __CHUNK_BLOCK_TYPES__:
        print("\n")
    
    return runnable.output
