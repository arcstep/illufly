import asyncio
import zmq.asyncio
import logging
import uuid

from typing import Union, List, Dict, Any, Optional, AsyncIterator, Iterator, Awaitable
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from enum import Enum
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from inspect import isasyncgenfunction, isgeneratorfunction, iscoroutinefunction

from .message_bus import MessageBusBase, MessageBusType, create_message_bus
from .models import ServiceConfig, StreamingBlock

logger = logging.getLogger(__name__)

class StreamingService(ABC):
    """基于ZMQ的流式服务"""

    def __init__(
        self,
        service_name: str=None,
        message_bus: MessageBusBase=None,
        service_config: ServiceConfig=None,
        logger=None
    ):
        service_name = service_name or self.__class__.__name__
        self.service_config = service_config or ServiceConfig(service_name=service_name)
        
        # 确保消息总线以服务端角色启动
        self.message_bus = message_bus or create_message_bus(MessageBusType.INPROC)
        
        self._logger = logger or logging.getLogger(self.service_config.service_name)
        self._running = False
        self._bind_event = asyncio.Event()
        self._context = zmq.asyncio.Context.instance()

    @abstractmethod
    def process(self, prompt: str, **kwargs) -> Union[
        StreamingBlock,  # 同步返回值
        Iterator[StreamingBlock],  # 同步生成器
        AsyncIterator[StreamingBlock],  # 异步生成器
        Awaitable[StreamingBlock]  # 异步返回值
    ]:
        """
        服务端处理请求的抽象方法，支持多种实现方式

        你应当重写这个方法实现流服务。
        """
        raise NotImplementedError

    def start(self) -> None:
        """启动服务"""

        loop = self._ensure_loop()
        if loop.is_running():
            raise RuntimeError("Cannot call start() from an async context. Use start_async() instead.")
        loop.run_until_complete(self.start_async())
        

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """确保有可用的事件循环，如果需要则创建新的"""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop
        
    async def start_async(self) -> None:
        """异步启动服务"""
        if self._running:
            self._logger.info("服务已经在运行中")
            return

        self._logger.info(f"开始启动服务 {self.service_config.service_name}")
        try:
            # 确保消息总线先启动
            if not self.message_bus._started:
                self._logger.debug("启动消息总线")
                
            # 初始化ZMQ资源
            self.rep_socket = self._context.socket(zmq.REP)
            self.rep_socket.bind(self.service_config.rep_address)
            self._logger.info(f"服务端socket绑定到地址: {self.service_config.rep_address}")
            
            # 创建共享状态
            self.threads = {}
            self._running = True
            
            # 启动消息处理循环任务
            self._receive_task = asyncio.create_task(self._receive_loop())
            
            # 设置就绪事件
            self._bind_event.set()
            
        except Exception as e:
            self._logger.error(f"服务启动失败: {e}")
            raise

    async def _receive_loop(self):
        """消息接收循环"""
        try:
            while self._running:
                try:
                    self._logger.debug("等待接收请求...")
                    request = await asyncio.wait_for(
                        self.rep_socket.recv_json(),
                        timeout=1.0
                    )
                    self._logger.info(f"收到请求: {request}")

                    command = request.get("command", "invalid_command")
                    if command == "init":
                        self._logger.debug("处理初始化请求")
                        thread_id = str(uuid.uuid4())
                        topics = {
                            "topic_chunk": f"stream.{thread_id}.chunk",
                            "topic_end": f"stream.{thread_id}.end",
                            "topic_error": f"stream.{thread_id}.error",
                        }
                        self.threads[thread_id] = topics
                        self._logger.debug(f"创建新线程 ID: {thread_id}, topics: {topics}")
                        await self.rep_socket.send_json({
                            "status": "success",
                            "thread_id": thread_id,
                            "topics": topics
                        })
                        
                    elif command == "process":
                        # 处理请求
                        thread_id = request.get("thread_id", "")
                        if not thread_id:
                            await self.rep_socket.send_json({"status": "error", "message": "Thread ID cannot be empty"})
                            continue

                        topics = self.threads.get(thread_id, {})
                        if not topics:
                            await self.rep_socket.send_json({"status": "error", "message": "Thread not found"})
                            continue

                        prompt = request.get("prompt", "")
                        kwargs = request.get("kwargs", {})
                        if not prompt:
                            await self.rep_socket.send_json({"status": "error", "message": "Prompt cannot be empty"})
                            continue

                        try:
                            async for block in self._adapt_process_request(prompt, **kwargs):
                                # 根据消息类型选择对应的 topic
                                if block.block_type == "end":
                                    topic = topics["topic_end"]
                                elif block.block_type == "error":
                                    topic = topics["topic_error"]
                                else:
                                    topic = topics["topic_chunk"]
                                    
                                self._logger.debug(f"Publishing to topic: {topic}, block: {block}")
                                await self.message_bus.publish(
                                    topic,
                                    block.model_dump(exclude_none=True)
                                )
                            await self.rep_socket.send_json({"status": "success"})
                        except Exception as e:
                            error_topic = topics["topic_error"]
                            self._logger.error(f"Error in process request: {e}")
                            await self.message_bus.publish(
                                error_topic,
                                StreamingBlock(block_type="error", content=str(e)).model_dump(exclude_none=True)
                            )
                            await self.rep_socket.send_json({"status": "error", "error": str(e)})
                        finally:
                            end_topic = topics["topic_end"]
                            self._logger.debug(f"Publishing end message to topic: {end_topic}")
                            await self.message_bus.publish(
                                end_topic,
                                StreamingBlock(block_type="end", content="").model_dump(exclude_none=True)
                            )
                            self.threads.pop(thread_id, None)
                        
                    elif command == "quit":
                        # 退出服务
                        self._running = False
                        await self.rep_socket.send_json({"status": "success"})
                        break
                    else:
                        # 未知命令
                        await self.rep_socket.send_json({"status": "error", "message": "Unknown command"})
                        continue
                    
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    self._logger.error(f"处理请求时发生错误: {e}")
                    await self.rep_socket.send_json({"status": "error", "error": str(e)})
                    
        except asyncio.CancelledError:
            self._logger.info("消息接收循环被取消")
        except Exception as e:
            self._logger.error(f"消息接收循环出错: {e}")
        finally:
            self._logger.info("消息接收循环结束")

    def stop(self) -> None:
        """同步停止服务"""
        loop = self._ensure_loop()
        if loop.is_running():
            raise RuntimeError("Cannot call stop() from an async context. Use stop_async() instead.")
        loop.run_until_complete(self.stop_async())
        
    async def stop_async(self) -> None:
        """异步停止服务"""
        if not self._running:
            return
            
        self._running = False
        self._bind_event.clear()
        
        # 取消并等待消息接收任务完成
        if hasattr(self, '_receive_task'):
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        # 清理资源
        if hasattr(self, 'rep_socket'):
            self.rep_socket.close()

    def _is_async_context(self) -> bool:
        """检测是否在异步上下文中"""
        try:
            loop = asyncio.get_running_loop()
            return True
        except RuntimeError:
            return False
            
    def __call__(self, prompt: str, **kwargs) -> Union[Iterator[StreamingBlock], AsyncIterator[StreamingBlock]]:
        """智能调用入口，根据上下文自动选择同步或异步方式"""
        if self._is_async_context():
            self._logger.debug("Detected async context, using async call")
            return self.call_async(prompt, **kwargs)
        else:
            self._logger.debug("Detected sync context, using sync call")
            return self.call(prompt, **kwargs)
    
    def call(self, prompt: str, **kwargs) -> Iterator[StreamingBlock]:
        """同步调用实现"""
        if not self._running:
            raise RuntimeError("Service not started")
            
        if not prompt:
            raise ValueError("Prompt cannot be Empty")
            
        self._logger.debug("Starting synchronous streaming request")
        loop = self._ensure_loop()
        
        async_iter = self.call_async(prompt, **kwargs)
        while True:
            try:
                block = loop.run_until_complete(async_iter.__anext__())
                yield block
            except StopAsyncIteration:
                break
            
    async def call_async(self, prompt: str, **kwargs) -> AsyncIterator[StreamingBlock]:
        """异步调用接口"""
        if not self._running:  # 修正条件判断
            raise RuntimeError("Service not started")
        
        if not prompt:
            raise ValueError("Prompt cannot be Empty")
        
        self._logger.info(f"开始异步流式请求: prompt={prompt}")
        
        try:
            # 等待服务端绑定完成
            await self._bind_event.wait()
            
            # 初始化连接
            req_socket = self._context.socket(zmq.REQ)
            req_socket.connect(self.service_config.rep_address)
            self._logger.info(f"客户端socket连接到地址: {self.service_config.rep_address}")

            # 初始化会话
            self._logger.debug("发送初始化请求")
            await req_socket.send_json({"command": "init"})
            response = await req_socket.recv_json()
            self._logger.debug(f"收到初始化响应: {response}")
            
            if response["status"] != "success":
                raise RuntimeError(f"初始化失败: {response.get('error', 'Unknown error')}")
            
            thread_id = response.get("thread_id")
            topics = response.get("topics", {})
            self._logger.info(f"会话初始化成功: thread_id={thread_id}")

            # 订阅消息通道
            self._logger.debug(f"订阅消息通道: {topics.values()}")
            subscription = self.message_bus.subscribe(list(topics.values()))

            # 发送处理请求
            self._logger.debug("发送处理请求")
            await req_socket.send_json({
                "command": "process",
                "thread_id": thread_id,
                "prompt": prompt,
                "kwargs": kwargs
            })
            
            response = await req_socket.recv_json()
            self._logger.debug(f"收到处理响应: {response}")
            
            if response["status"] != "success":
                raise RuntimeError(f"处理请求失败: {response.get('error', 'Unknown error')}")

            # 接收流式响应
            self._logger.info("开始接收流式响应")
            async with asyncio.timeout(10):
                async for block in subscription:
                    self._logger.debug(f"收到消息块: {block}")
                    if block.get("error"):
                        raise RuntimeError(block["error"])
                    elif block.get("block_type") == "end":
                        self._logger.info("流式响应完成")
                        yield StreamingBlock(**block)
                        break
                    else:
                        yield StreamingBlock(**block)

        except Exception as e:
            self._logger.error(f"流式请求处理失败: {e}")
            raise
        finally:
            if 'req_socket' in locals():
                req_socket.close()
        
    async def _adapt_process_request(self, prompt: str, **kwargs) -> AsyncIterator[StreamingBlock]:
        """适配不同的 process 实现为统一的异步迭代器"""
        result = self.process(prompt, **kwargs)
        
        # 检查实现类型
        if isasyncgenfunction(self.process):
            # 异步生成器
            self._logger.debug("Using async generator implementation")
            async for block in result:
                yield block
                
        elif isgeneratorfunction(self.process):
            # 同步生成器
            self._logger.debug("Using sync generator implementation")
            for block in result:
                yield block
                
        elif iscoroutinefunction(self.process):
            # 异步返回值
            self._logger.debug("Using async return implementation")
            block = await result
            yield block
            
        else:
            # 同步返回值
            self._logger.debug("Using sync return implementation")
            yield result

    def __enter__(self) -> 'BaseStreamingService':
        """同步上下文管理器入口"""
        self.start()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """同步上下文管理器退出"""
        self.stop()
        
    async def __aenter__(self) -> 'BaseStreamingService':
        """异步上下文管理器入口"""
        await self.start_async()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器退出"""
        await self.stop_async() 
