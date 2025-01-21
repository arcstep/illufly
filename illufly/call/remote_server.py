import os
import logging
import json
import time
import uuid
import asyncio
import threading

from typing import List, Union, Dict, Any, Optional, AsyncGenerator, Generator

from ..mq import StreamingBlock, BlockType, Publisher, Replier, ErrorBlock
from .base_call import BaseCall

class RemoteServer(BaseCall):
    """远程服务端"""

    def __init__(
        self,
        service_name: str=None,
        publisher_address: str = None,
        server_address: str = None,
        timeout: float = 30.0,
        poll_interval: int = 500,
        **kwargs
    ):
        """初始化服务
        
        Args:
            service_name: 服务名称
            publisher_address: 发布者地址
            server_address: 服务端地址
            timeout: 超时时间
            poll_interval: 轮询间隔(毫秒)，默认500ms
        """
        super().__init__(**kwargs)
        self._service_name = service_name or f"{self.__class__.__name__}.{self.__hash__()}"
        self._publisher_address = publisher_address
        self._server_address = server_address
        self._tasks = set()
        self._logger.info(f"Initialized RemoteServer with service_name={self._service_name}, server_address={self._server_address}, publisher_address={self._publisher_address}")
        
        self.register_method("reply_handler", async_handle=self._async_handler)
        
        # 初始化发布者
        if self._publisher_address:
            self._publisher = Publisher(address=self._publisher_address, logger=self._logger)
        else:
            raise ValueError("publisher_address is required")
        
        # 初始化服务端
        if self._server_address:
            self._server = Replier(address=self._server_address, logger=self._logger)
        else:
            raise ValueError("server_address is required")

        # 启动服务端
        self._start_server()

    async def _async_handler(self, *args, thread_id: str, publisher, **kwargs):
        """回复处理函数"""
        pass

    def __del__(self):
        """析构函数"""
        self._logger.info("SimpleService being destroyed")
        try:
            self.cleanup()
        except Exception as e:
            self._logger.info(f"Error during cleanup in __del__: {e}")

    def cleanup(self):
        """清理资源"""
        try:
            loop = asyncio.get_running_loop()
            self._logger.info(f"Got running loop {id(loop)}")
            if not loop.is_closed():
                self._logger.info(f"Cleaning up {len(self._tasks)} tasks")
                for task in self._tasks:
                    if not task.done():
                        self._logger.info(f"Cancelling task {id(task)}")
                        task.cancel()
        except RuntimeError as e:
            self._logger.info(f"No running event loop available: {e}")
        except Exception as e:
            self._logger.info(f"Error during cleanup: {e}")
        finally:
            if self._publisher_address and hasattr(self, '_publisher'):
                self._logger.info("Cleaning up publisher")
                self._publisher.cleanup()

    async def _process_and_end(self, *args, thread_id: str, **kwargs):
        """将处理和结束标记合并为一个顺序任务"""
        task_id = id(asyncio.current_task())
        self._logger.info(f"Process task {task_id} starting for thread {thread_id}")
        try:
            # 执行实际的服务方法
            await self.async_method(
                "reply_handler",
                *args,
                thread_id=thread_id,
                publisher=self._publisher,
                **kwargs
            )
            self._logger.info(f"Process task {task_id} completed normally for thread_id={thread_id}")
        except Exception as e:
            self._logger.error(f"Process task {task_id} failed with error: {e}")
            self._publisher.publish(
                topic=thread_id,
                message=ErrorBlock(error=str(e))
            )
        finally:
            self._publisher.end(topic=thread_id)
            self._logger.info(f"Process task {task_id} entering finished for thread: {thread_id}")

    def _start_server(self):
        """启动服务端"""
        try:
            async def echo_handler(data):
                """简单的回显处理函数"""
                self._logger.info(f"Received data: {data}")
                thread_id = data.get("thread_id", None)
                if not thread_id:
                    self._logger.error("thread_id is required")
                    self._publisher.publish(topic=thread_id, message=ErrorBlock(error="thread_id is required"))
                    return

                args = data.get("args", [])
                kwargs = data.get("kwargs", {})
                await self._process_and_end(*args, thread_id=thread_id, **kwargs)

            task = asyncio.create_task(self._server.async_reply(echo_handler))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

        except Exception as e:
            self._logger.error(f"Error starting server: {e}")
            raise e
