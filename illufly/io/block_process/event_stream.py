# import logging
from typing import Union
from ..block import EventBlock

def event_stream(block: Union[EventBlock, str], verbose: bool=False, **kwargs):
    """
    生成适合于 Web 处理的 SSE 事件流格式的数据。

    如果使用 FastAPI，则可以使用 `event_stream` 作为 `EventSourceResponse` 的生成器。
    """

    if isinstance(block, EventBlock):
        return {
            "data": {
                "block_type": block.block_type,
                "content": block.text,
                "thread_id": block.runnable_info.get("thread_id", None),
                "calling_id": block.runnable_info["calling_id"],
                "agent_name": block.runnable_info["name"]
            }
        }
    elif isinstance(block, str):
        return {
            "data": {
                "content": block,
            }
        }
    else:
        # logging.error(f"Unknown block type: {block}")
        # 在生产环境中，可能不想中断整个流，而是跳过无效的块
        pass
