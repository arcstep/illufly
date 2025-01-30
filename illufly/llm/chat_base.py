from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union

import uuid
import logging

from ..io.rocksdict import default_rocksdb, IndexedRocksDB
from ..llm.memory.L0_qa import QAManager, QA, Message
from ..call import RemoteServer
from ..mq import Publisher, StreamingBlock, BlockType, TextChunk
from .system_template import SystemTemplate

class ChatBase(RemoteServer, ABC):
    """Base Chat Service

    注意，因为不在远程 REP 方法中持久化 Chat 相关数据，因此相关数据管理方法也在客户端实现。
    服务端只负责分发请求，不负责请求数据持久化，就可以支持分布式的 Chat 服务部署。
    分布式 Chat 部署可以带来的好处：
    - 允许服务端独立，可以支持多用户访问时的背压控制，这在企业级场景中需要对资源使用授权时非常有用
    - 允许服务端独立，可以通过 Router 模式实现负载均衡的升级模式
    - 客户端在进程内管理 rocksdb 数据符合最佳实践，方便结合 fastapi 和 traefik 部署

    最佳实践：
    - 仅为 system 消息使用模板
    - 模板中的变量可以在调用时由 bindings 指定，也可以由绑定到内置的上下文专有变量

    按照多种维度，根据问题转换上下文环境：
    - 多轮对话
    - 工具回调
    - 概念清单
    - 思考方法
    - 思考习惯
    - 样本示例
    - 资料检索
    - 网络搜索
    - 数据集描述
    ...
    """
    def __init__(
        self,
        user_id: str = None,
        db: IndexedRocksDB = None,
        thread_id: str = None,
        **kwargs
    ):
        super().__init__(**kwargs)

        self.user_id = user_id or "default"
        self.db = db or default_rocksdb
        self._logger = logging.getLogger(__name__)

        self.l0_qa = QAManager(db=self.db, user_id=user_id)
        if thread_id:
            self.load_thread(thread_id)
        else:
            last_thread = self.l0_qa.last_thread()
            if not last_thread:
                last_thread = self.l0_qa.create_thread()
            self.thread = last_thread

    @property
    def all_threads(self):
        return self.l0_qa.all_threads()
    
    @property
    def thread_id(self):
        return self.thread.thread_id

    @property
    def history(self):
        return self.l0_qa.retrieve(self.thread_id)
    
    @property
    def history_messages(self):
        return [m.message_dict for m in self.history]

    @property
    def all_qas(self):
        return self.l0_qa.get_all(self.thread_id)

    def new_thread(self):
        """创建一个新的对话"""
        self.thread = self.l0_qa.create_thread()
    
    def load_thread(self, thread_id: str):
        """从历史对话加载"""
        thread = self.l0_qa.get_thread(thread_id)
        if not thread:
            raise ValueError(f"对话 {thread_id} 不存在")
        self.thread = thread

    def normalize_messages(self, messages: Union[str, List[Dict[str, Any]]]):
        """规范化消息"""
        self._logger.info(f"messages: {messages}")
        _messages = messages if isinstance(messages, list) else [messages]
        return [Message.create(m) for m in _messages]

    def create_request_id(self, request_id: str = ""):
        """创建请求ID"""
        if not request_id:
            request_id = f"{self.service_name}.{uuid.uuid4()}"
        return request_id

    async def async_call(
        self,
        messages: Union[str, List[Dict[str, Any]]],
        block_types: List[BlockType] = None,
        system_template: SystemTemplate = None,
        bindings: Dict[str, Any] = None,
        **kwargs
    ):
        """异步调用远程服务"""
        block_types = block_types or [BlockType.TEXT_CHUNK, BlockType.USAGE, BlockType.ERROR]
        normalized_messages = self.normalize_messages(messages)
        patched_messages = self.before_call(normalized_messages, system_template, bindings)

        # 远程调用
        request_id = self.create_request_id()
        sub = await self._requester.async_request(
            kwargs={"messages": patched_messages, **kwargs},
            request_id=request_id
        )
        final_text = ""
        async for b in sub.async_collect(block_types=block_types):
            if b.block_type == BlockType.TEXT_CHUNK:
                final_text += b.text
            yield b
        
        # 写入认知上下文
        output_messages = [Message(role="assistant", content=final_text)]
        self.after_call(normalized_messages, output_messages, request_id=request_id, **kwargs)

    def call(
        self,
        messages: Union[str, List[Dict[str, Any]]],
        block_types: List[BlockType] = None,
        system_template: SystemTemplate = None,
        bindings: Dict[str, Any] = None,
        **kwargs
    ):
        """同步调用远程服务"""
        block_types = block_types or [BlockType.TEXT_CHUNK, BlockType.USAGE, BlockType.ERROR]
        normalized_messages = self.normalize_messages(messages)
        patched_messages = self.before_call(normalized_messages, system_template, bindings)

        # 远程调用
        request_id = self.create_request_id()
        sub = self._requester.request(
            kwargs={"messages": patched_messages, **kwargs},
            request_id=request_id
        )
        final_text = ""
        for b in sub.collect(block_types=block_types):
            if b.block_type == BlockType.TEXT_CHUNK:
                final_text += b.text
            yield b
        
        # 写入认知上下文
        output_messages = [Message(role="assistant", content=final_text)]
        self.after_call(normalized_messages, output_messages, request_id=request_id, **kwargs)

    def before_call(self, input_messages: List[Message], system_template: SystemTemplate, bindings: Dict[str, Any]):
        """补充认知上下文"""

        # 从认知上下文中获取消息
        patched_messages = self.l0_qa.retrieve(self.thread_id, messages=input_messages)

        # 如果系统消息不存在，则补充系统消息
        if patched_messages[0].role != "system" and system_template:
            bindings = bindings or {}
            system_message = system_template.format(variables=bindings)
            patched_messages.insert(0, Message(role="system", content=system_message))

        return [m.message_dict for m in patched_messages]

    def after_call(self, input_messages: List[Message], output_messages: List[Message], request_id: str, **kwargs):
        """回写认知上下文"""

        # 处理输出消息
        qa_messages = input_messages + output_messages
        qa = QA(
            qa_id=request_id,
            user_id=self.user_id,
            thread_id=self.thread_id,
            messages=qa_messages
        )
        self.l0_qa.add_qa(qa)

    ## ***********************************************************************
    ## 以下是 ZMQ 远程 REP 服务方法实现
    ## 注意，客户端在请求后自己管理 rocksdb 数据，而不是通过远程方法
    ## ***********************************************************************

    @abstractmethod
    async def _async_handler(
        self,
        messages: Union[str, List[Dict[str, Any]]],
        request_id: str, # RemoteServer 要求的参数
        publisher: Publisher, # RemoteServer 要求的参数
        **kwargs
    ):
        """要求在子类中实现
        
        Args:
            messages: 输入消息
            request_id: 请求ID（RemoteServer 要求的参数）
            publisher: 发布者（RemoteServer 要求的参数）
            **kwargs: 其他用户自定义参数
        """
        pass

