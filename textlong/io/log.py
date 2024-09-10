import json

from typing import Callable, Iterable, Union, AsyncIterable
from .block import TextBlock

def log(resp: Union[Iterable[TextBlock], Iterable[str]]):
    """
    针对任何回调函数，只要符合规范的返回TextBlock对象的生成器，就可以使用这个函数来
    打印流式日志。

    返回值中，tools_call可以方便处理智能体的工具回调。
    """

    output_text = ""
    last_block_type = ""

    for block in resp:
        if isinstance(block, TextBlock):
            if block.block_type in ['text', 'chunk', 'front_matter']:
                output_text += block.text
            
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
                print(f'[{block.block_type.upper()}] {block.text_with_print_color}')
        elif isinstance(block, str):
            print(block)
            output_text += block
        else:
            raise ValueError(f"Unknown block type: {block}")
        
    if last_block_type in ["chunk", "tool_resp_chunk"]:
        print("\n")
        last_block_type = ""
    
    return output_text

async def alog(resp: Union[AsyncIterable[TextBlock], AsyncIterable[str]]):
    """
    针对任何回调函数，只要符合规范的返回TextBlock对象的生成器，就可以使用这个函数来
    打印流式日志。

    返回值中，tools_call可以方便处理智能体的工具回调。
    """

    output_text = ""
    last_block_type = ""

    async for block in resp:
        if isinstance(block, TextBlock):
            if block.block_type in ['text', 'chunk', 'front_matter']:
                output_text += block.text
            
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
                print(f'[{block.block_type.upper()}] {block.text_with_print_color}')
        elif isinstance(block, str):
            print(block)
            output_text += block
        else:
            raise ValueError(f"Unknown block type: {block}")
        
    if last_block_type in ["chunk", "tool_resp_chunk"]:
        print("\n")
        last_block_type = ""
    
    return output_text
