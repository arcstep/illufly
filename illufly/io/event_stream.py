import json
from typing import AsyncIterable, Union
import logging
import asyncio

from .block import EventBlock

async def event_stream(runnable: "Runnable", *args, **kwargs):
    """
    生成适合于 Web 处理的 SSE 事件流格式的数据。
    """

    resp = runnable.async_call(*args, **kwargs)
    async for block in resp:
        if isinstance(block, EventBlock):
            yield f"event: {block.block_type}\ndata: {block.text}\n\n"
        elif isinstance(block, str):
            yield f"data: {block}\n\n"
        else:
            # logging.error(f"Unknown block type: {block}")
            # 在生产环境中，可能不想中断整个流，而是跳过无效的块
            continue
        await asyncio.sleep(0)
