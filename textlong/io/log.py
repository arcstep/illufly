import json

from typing import Callable, Iterable, Union, AsyncIterable
from .block import TextBlock
from ..base import CallBase

def process_block(block, last_block_type, output_text):
    if isinstance(block, TextBlock):
        if block.block_type in ['text', 'chunk', 'front_matter']:
            output_text += block.text
        elif block.block_type in ['text_final', 'tool_resp_final']:
            output_text = block.text
            
        if block.block_type in ['chunk', 'tool_resp_chunk']:
            if last_block_type in ["chunk", "tool_resp_chunk"] and last_block_type != block.block_type:
                print("\n")
            last_block_type = block.block_type
            print(block.text_with_print_color, end="")
        else:
            if last_block_type in ["chunk", "tool_resp_chunk"]:
                print("\n")
                last_block_type = ""
            last_block_type = block.block_type
            if block.block_type not in ["text_final"]:
                print(f'[{block.block_type.upper()}] {block.text_with_print_color}')
    elif isinstance(block, str):
        print(block)
        output_text += block
    else:
        raise ValueError(f"Unknown block type: {block}")
    
    return last_block_type, output_text

def log(call_obj: CallBase, *args, **kwargs):
    """
    针对任何回调函数，只要符合规范的返回TextBlock对象的生成器，就可以使用这个函数来
    打印流式日志。

    返回值中，tools_call可以方便处理智能体的工具回调。
    """

    output_text = ""
    last_block_type = ""

    resp = call_obj.call(*args, **kwargs)
    for block in resp:
        last_block_type, output_text = process_block(block, last_block_type, output_text)
        
    if last_block_type in ["chunk", "tool_resp_chunk"]:
        print("\n")
        last_block_type = ""
    
    return output_text

async def alog(call_obj: CallBase, *args, **kwargs):
    """
    针对任何回调函数，只要符合规范的返回TextBlock对象的生成器，就可以使用这个函数来
    打印流式日志。

    返回值中，tools_call可以方便处理智能体的工具回调。
    """

    output_text = ""
    last_block_type = ""

    resp = call_obj.async_call(*args, **kwargs)
    async for block in resp:
        last_block_type, output_text = process_block(block, last_block_type, output_text)
        
    if last_block_type in ["chunk", "tool_resp_chunk"]:
        print("\n")
        last_block_type = ""
    
    return output_text
