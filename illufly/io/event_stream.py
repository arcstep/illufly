import json
from typing import AsyncIterable, Union
import logging
import asyncio

from .block import EventBlock

async def event_stream(block, verbose: bool=False, **kwargs):
    """
    生成适合于 Web 处理的 SSE 事件流格式的数据。
    """

    if isinstance(block, EventBlock):
        yield f"event: {block.block_type}\ndata: {block.text}\n\n"
    elif isinstance(block, str):
        yield f"data: {block}\n\n"
    else:
        # logging.error(f"Unknown block type: {block}")
        # 在生产环境中，可能不想中断整个流，而是跳过无效的块
        pass
    await asyncio.sleep(0)
