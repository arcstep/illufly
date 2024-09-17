import json
from typing import AsyncIterable, Union
import logging
import asyncio

from .block import TextBlock
from ..core.agent import Runnable

async def event_stream(runnable: Runnable, *args, **kwargs):
    """
    针对任何回调函数，只要符合规范的返回 TextBlock 对象或 str 的生成器，就可以使用这个函数来
    生成事件流格式的数据。
    """

    resp = runnable.async_call(*args, **kwargs)
    async for block in resp:
        if isinstance(block, TextBlock):
            yield f"event: {block.block_type}\ndata: {block.content}\n\n"
        elif isinstance(block, str):
            yield f"data: {block}\n\n"
        else:
            # logging.error(f"Unknown block type: {block}")
            # 在生产环境中，可能不想中断整个流，而是跳过无效的块
            continue
        await asyncio.sleep(0)
