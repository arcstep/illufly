import json
from typing import AsyncIterable, Union
from .block import TextBlock
import logging
import asyncio

async def event_stream(resp: AsyncIterable[Union[TextBlock, str]]):
    """
    针对任何回调函数，只要符合规范的返回TextBlock对象或str的生成器，就可以使用这个函数来
    生成事件流格式的数据。
    """

    async for block in resp:
        if isinstance(block, TextBlock):
            # logging.info(f"Sending block: {block.block_type} - {block.content}")
            yield f"event: {block.block_type}\ndata: {block.content}\n\n"
        elif isinstance(block, str):
            # logging.info(f"Sending string block: {block}")
            yield f"data: {block}\n\n"
        else:
            # logging.error(f"Unknown block type: {block}")
            # 在生产环境中，可能不想中断整个流，而是跳过无效的块
            continue
        await asyncio.sleep(0)
