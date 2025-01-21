import os
import logging
import json
import time
import uuid
import asyncio
import threading

from typing import List, Union, Dict, Any, Optional, AsyncGenerator, Generator

from ..mq import Publisher, Replier
from .base_call import BaseCall

class RemoteServer(BaseCall):
    """远程服务端"""

    def __init__(
        self,
        service_name: str=None,
        publisher_address: str = None,
        server_address: str = None,
        timeout: int = 30*1000,
        max_concurrent_tasks=100,
        **kwargs
    ):
        """初始化服务
        
        Args:
            service_name: 服务名称
            publisher_address: 发布者地址
            server_address: 服务端地址
            timeout: 超时时间
            max_concurrent_tasks: 最大并发任务数
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

        self._active_tasks = {}  # 使用字典跟踪活动任务
        self._max_concurrent_tasks = max_concurrent_tasks
        self._task_semaphore = asyncio.Semaphore(max_concurrent_tasks)
        
        # 启动清理监控任务
        self._cleanup_task = asyncio.create_task(self._cleanup_monitor())
        self._tasks.add(self._cleanup_task)  # 将清理任务添加到任务集合中
        
        # 启动服务端
        self.start_server()

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

    async def async_cleanup(self):
        """异步清理资源"""
        try:
            # 首先取消清理监控任务
            if hasattr(self, '_cleanup_task') and not self._cleanup_task.done():
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    self._logger.info("Cleanup monitor task cancelled")

            # 然后清理其他任务
            if self._tasks:
                self._logger.info(f"Cleaning up {len(self._tasks)} tasks")
                # 创建任务列表的副本进行遍历
                tasks = list(self._tasks)
                for task in tasks:
                    if not task.done():
                        self._logger.info(f"Cancelling task {id(task)}")
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            self._logger.info(f"Task {id(task)} cancelled")
                        except Exception as e:
                            self._logger.error(f"Error while cancelling task {id(task)}: {e}")

                # 清空任务集合
                self._tasks.clear()
                
        finally:
            # 清理其他资源
            if self._publisher_address and hasattr(self, '_publisher'):
                self._logger.info("Cleaning up publisher")
                self._publisher.cleanup()
            if hasattr(self, '_server'):
                self._logger.info("Cleaning up server")
                self._server.cleanup()

    def cleanup(self):
        """同步清理资源"""
        try:
            loop = asyncio.get_running_loop()
            if not loop.is_closed():
                loop.run_until_complete(self.async_cleanup())
        except RuntimeError:
            # 如果没有运行中的事件循环，创建一个新的
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.async_cleanup())
            finally:
                loop.close()

    async def _process_and_end(self, *args, thread_id: str, **kwargs):
        async with self._task_semaphore:  # 限制并发任务数
            task = asyncio.current_task()
            self._active_tasks[thread_id] = task
            try:
                await self.async_method(
                    "reply_handler",
                    *args,
                    thread_id=thread_id,
                    publisher=self._publisher,
                    **kwargs
                )
            finally:
                self._publisher.end(thread_id=thread_id)
                self._active_tasks.pop(thread_id, None)  # 清理完成的任务

    async def cancel_thread(self, thread_id: str):
        """取消特定线程的任务"""
        if thread_id in self._active_tasks:
            task = self._active_tasks[thread_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    def start_server(self):
        """改进的服务启动方法"""
        try:
            task = asyncio.create_task(self._server.async_reply(self._process_and_end))
            self._tasks.add(task)
            
            def handle_task_done(task):
                self._tasks.discard(task)
                try:
                    # 获取任务的结果或异常
                    task.result()
                except asyncio.CancelledError:
                    self._logger.info("Task was cancelled")
                except Exception as e:
                    self._logger.error(f"Task failed with error: {e}")
                
            task.add_done_callback(handle_task_done)

        except Exception as e:
            self._logger.error(f"Error starting server: {e}")
            raise e

    async def _cleanup_monitor(self):
        """定期清理过期任务"""
        self._logger.info("Starting cleanup monitor")
        while True:
            try:
                # 清理已完成的任务
                completed_tasks = {thread_id for thread_id, task in self._active_tasks.items() 
                                if task.done()}
                for thread_id in completed_tasks:
                    task = self._active_tasks.pop(thread_id)
                    try:
                        await task  # 获取任何未处理的异常
                    except Exception as e:
                        self._logger.error(f"Task {thread_id} failed: {e}")
                
                # 记录当前活动任务数量
                active_count = len(self._active_tasks)
                if active_count > 0:
                    self._logger.debug(f"Current active tasks: {active_count}")
                
                await asyncio.sleep(60)  # 每分钟检查一次
            except asyncio.CancelledError:
                self._logger.info("Cleanup monitor cancelled")
                break
            except Exception as e:
                self._logger.error(f"Cleanup monitor error: {e}")
                await asyncio.sleep(60)  # 发生错误时等待后重试
