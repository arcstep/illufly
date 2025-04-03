from typing import List, Dict, Any, Union, Optional, AsyncGenerator, Tuple, Type
from pydantic import BaseModel, Field

from ..rocksdb import default_rocksdb, IndexedRocksDB
from .base import LiteLLM
from .models import ChunkType, DialougeChunk, ToolCalling, MemoryQA
from .memory import Memory
from .retriever import ChromaRetriever
from .thread import ThreadManager
from .base_tool import BaseTool

from datetime import datetime
import asyncio
import json
import logging
logger = logging.getLogger(__name__)

class ChatAgent():
    """对话智能体"""
    def __init__(
        self, 
        db: IndexedRocksDB=None, 
        memory: Memory=None, 
        tools: List[Type[BaseTool]]=None,
        **kwargs
    ):
        self.llm = LiteLLM(**kwargs)
        self.db = db or default_rocksdb
        self.memory = memory or Memory(llm=self.llm, memory_db=self.db)
        self.thread_manager = ThreadManager(db=self.db)
        self.tools = tools or []
        
        # 创建工具名称到工具类的映射
        self.tool_map = {tool.name: tool for tool in self.tools}

        self.recent_messages_count = 10
        DialougeChunk.register_indexes(self.db)

        logger.info(f'数据库中有 {len(self.db.values())} 条对话记录 ...')

    def register_tool(self, tool_class: Type[BaseTool]) -> None:
        """注册工具到对话智能体"""
        if tool_class.name in self.tool_map:
            logger.warning(f"工具 '{tool_class.name}' 已存在，将被覆盖")
        
        self.tools.append(tool_class)
        self.tool_map[tool_class.name] = tool_class
        logger.info(f"已注册工具: {tool_class.name}")

    async def chat(self, messages: List[Dict[str, Any]], model: str, user_id: str=None, thread_id: str=None, **kwargs):
        """对话主流程
        
        协调各个处理模块，完成完整的对话流程：
        1. 加载历史 + 检索记忆
        2. 注入记忆 + 保存用户输入
        3. 并行执行：提取新记忆 + 对话补全
        """
        if not messages:
            raise ValueError("messages 不能为空")

        # 标准化用户输入
        messages = self._normalize_input_messages(messages)
        
        # 1. 加载历史消息
        history_messages = await self._load_history_messages(user_id, thread_id)
        is_first_conversation = len(history_messages) == 0
        
        messages = self._merge_messages(messages, history_messages)
        
        # 2. 检索记忆
        retrieved_memories = await self.memory.retrieve(messages, user_id)
        
        # 3. 发送检索到的记忆
        if retrieved_memories:
            memory_chunks = await self._process_retrieved_memories(retrieved_memories, user_id, thread_id)
            for chunk in memory_chunks:
                yield chunk
        
        # 4. 注入记忆到提示中
        messages, memory_table = self._inject_memory(messages, retrieved_memories)
        
        # 5. 保存用户输入
        input_created_at = datetime.now().timestamp()
        await self._save_user_input(messages, user_id, thread_id, input_created_at)
        
        # 6. 并行执行记忆提取和对话补全
        extract_task = asyncio.create_task(
            self.memory.extract(messages, model, memory_table, user_id)
        )
        
        # 7. 创建LLM配置并添加工具
        llm_kwargs = kwargs.copy()
        if self.tools and not llm_kwargs.get("tools"):
            llm_kwargs["tools"] = [tool.to_openai() for tool in self.tools]
        
        # 8. 执行对话流程 (可能包括多轮工具调用)
        final_text = ""
        final_tool_calls = {}
        
        conversation_processor = ConversationProcessor(
            llm=self.llm,
            model=model,
            user_id=user_id,
            thread_id=thread_id,
            tool_map=self.tool_map,
            save_chunk_callback=self.save_dialog_chunk
        )
        
        # 开始对话处理，可能包含多轮工具调用
        async for chunk in conversation_processor.process_conversation(messages, **llm_kwargs):
            # 记录最终的文本和工具调用结果
            if isinstance(chunk, dict):
                if chunk.get("chunk_type") == ChunkType.AI_MESSAGE.value:
                    final_text = chunk.get("output_text", "")
                    if chunk.get("tool_calls"):
                        final_tool_calls = {tc["tool_id"]: tc for tc in chunk.get("tool_calls", [])}
            
            # 将处理后的数据传递给调用者
            yield chunk
        
        # 9. 等待记忆提取完成并处理结果
        extracted_memories = await extract_task
        if extracted_memories:
            async for chunk in self._process_extracted_memories(extracted_memories, user_id, thread_id):
                yield chunk
        
        # 10. 如果是首轮对话，生成标题
        if is_first_conversation and user_id and thread_id and final_text:
            async for chunk in self._generate_title(messages, final_text, model, user_id, thread_id):
                yield chunk

    def _normalize_input_messages(self, messages: Union[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """标准化输入消息格式"""
        if isinstance(messages, str):
            return [{"role": "user", "content": messages}]
        
        if not isinstance(messages, list):
            raise ValueError("messages 必须是形如 [{'role': 'user', 'content': '用户输入'}, ...] 的列表")
            
        return messages

    async def _load_history_messages(self, user_id: str=None, thread_id: str=None) -> List[Dict[str, Any]]:
        """加载历史消息"""
        if not user_id or not thread_id:
            return []
        return self.load_history(user_id, thread_id, limit=self.recent_messages_count)
    
    def _merge_messages(self, messages: List[Dict[str, Any]], history_messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """合并当前消息和历史消息"""
        if messages[0].get("role", None) == "system":
            return [messages[0], *history_messages, *messages[1:]]
        else:
            return [*history_messages, *messages]
    
    async def _process_retrieved_memories(
        self,
        retrieved_memories: List[MemoryQA],
        user_id: str=None,
        thread_id: str=None
    ) -> List[Dict[str, Any]]:
        """处理检索到的记忆，将其保存并准备发送"""
        memory_chunks = []
        for memory in retrieved_memories:
            memory_chunk = DialougeChunk(
                user_id=user_id,
                thread_id=thread_id,
                chunk_type=ChunkType.MEMORY_RETRIEVE,
                role="assistant",
                memory=memory
            )
            self.save_dialog_chunk(memory_chunk)
            memory_chunks.append(memory_chunk.model_dump())
        return memory_chunks
    
    def _inject_memory(
        self,
        messages: List[Dict[str, Any]],
        retrieved_memories: List[MemoryQA]
    ) -> Tuple[List[Dict[str, Any]], str]:
        """将检索到的记忆注入到消息中"""
        # 将记忆转化为表格形式
        memory_table = ""
        if retrieved_memories:
            items = [f'|{m.topic}|{m.question}|{m.answer}|' for m in retrieved_memories]
            memory_table = f"\n\n|主题|问题|答案|\n|---|---|---|\n{chr(10).join(items)}\n"
        
        # 注入记忆到消息中
        injected_messages = self.memory.inject(messages, memory_table)
        
        return injected_messages, memory_table
    
    async def _save_user_input(
        self, 
        messages: List[Dict[str, Any]], 
        user_id: str=None, 
        thread_id: str=None,
        created_at: float=None
    ) -> None:
        """保存用户输入"""
        dialog_chunk = DialougeChunk(
            user_id=user_id,
            thread_id=thread_id,
            chunk_type=ChunkType.USER_INPUT,
            input_messages=messages,
            created_at=created_at or datetime.now().timestamp()
        )
        self.save_dialog_chunk(dialog_chunk)
    
    def _create_llm_response_processor(self, model: str, user_id: str=None, thread_id: str=None):
        """创建LLM响应处理器"""
        return LLMResponseProcessor(self.llm, model, user_id, thread_id)

    async def _save_ai_output(
        self, 
        final_text: str, 
        final_tool_calls: Dict[str, ToolCalling], 
        user_id: str=None, 
        thread_id: str=None
    ) -> None:
        """保存AI输出"""
        # 保存文本输出
        if final_text:
            dialog_chunk = DialougeChunk(
                user_id=user_id,
                thread_id=thread_id,
                chunk_type=ChunkType.AI_MESSAGE,
                output_text=final_text
            )
            self.save_dialog_chunk(dialog_chunk)
        
        # 保存工具调用
        if final_tool_calls:
            dialog_chunk = DialougeChunk(
                user_id=user_id,
                thread_id=thread_id,
                chunk_type=ChunkType.AI_MESSAGE,
                tool_calls=list(final_tool_calls.values())
            )
            self.save_dialog_chunk(dialog_chunk)
            yield dialog_chunk.model_dump()
    
    async def _process_extracted_memories(
        self, 
        extracted_memories: List[MemoryQA], 
        user_id: str=None, 
        thread_id: str=None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """处理提取的记忆"""
        if not extracted_memories:
            return
            
        for memory in extracted_memories:
            memory_chunk = DialougeChunk(
                user_id=user_id,
                thread_id=thread_id,
                chunk_type=ChunkType.MEMORY_EXTRACT,
                memory=memory
            )
            self.save_dialog_chunk(memory_chunk)
            yield memory_chunk.model_dump()
    
    async def _generate_title(
        self, 
        messages: List[Dict[str, Any]], 
        final_text: str, 
        model: str, 
        user_id: str=None, 
        thread_id: str=None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """为首轮对话生成标题"""
        # 构建生成标题的提示
        user_content = messages[-1].get("content", "") if messages else ""
        title_prompt = [
            {"role": "system", "content": "你是一个对话标题生成助手。请根据用户的消息和AI的回复，提炼出一个简短、准确的对话标题，不超过15个字。只需返回标题本身，不要包含任何其他文字或标点。"},
            {"role": "user", "content": f"用户消息：{user_content}\nAI回复：{final_text}\n请生成一个简短的对话标题："}
        ]
        
        try:
            # 调用LLM生成标题
            title_resp = await self.llm.acompletion(title_prompt, model=model, stream=False)
            if title_resp and title_resp.choices and title_resp.choices[0].message.content:
                title = title_resp.choices[0].message.content.strip()
                # 限制标题长度
                if len(title) > 20:
                    title = title[:20]
                
                # 更新Thread的标题
                updated_thread = self.thread_manager.update_thread_title(user_id, thread_id, title)
                
                if updated_thread:
                    # 创建标题更新通知
                    title_chunk = DialougeChunk(
                        user_id=user_id,
                        thread_id=thread_id,
                        chunk_type=ChunkType.TITLE_UPDATE,
                        output_text=title
                    )
                    self.save_dialog_chunk(title_chunk)
                    yield title_chunk.model_dump()
        except Exception as e:
            logger.error(f"生成标题失败: {e}")
            # 标题生成失败不影响正常对话流程，可以静默失败

    def save_dialog_chunk(self, chunk: DialougeChunk):
        """保存对话片段

        仅当用户ID和线程ID存在时，才保存对话片段
        """
        if chunk.user_id and chunk.thread_id:
            key = DialougeChunk.get_key(chunk.user_id, chunk.thread_id, chunk.dialouge_id)
            logger.info(f"\nsave_dialog_chunk >>> key: {key}, chunk: {chunk}")
            self.db.update_with_indexes(
                model_name=DialougeChunk.__name__,
                key=key,
                value=chunk
            )

    def load_history(self, user_id: str, thread_id: str, limit: int = 100):
        """加载历史对话"""
        prefix = DialougeChunk.get_prefix(user_id, thread_id)
        logger.info(f"加载历史对话 - 用户ID: {user_id}, 线程ID: {thread_id}, 前缀: {prefix}, 限制: {limit}")
        
        resp = sorted(
            self.db.values(
                prefix=prefix,
                limit=limit,
                reverse=True
            ),
            key=lambda x: x.created_at
        )
        messages = []
        logger.info(f"找到 {len(resp)} 条历史对话记录 ...")
        for m in resp:
            logger.info(f"\nload_history >>> {m}")
            if m.chunk_type == ChunkType.USER_INPUT:
                messages.append({
                    "role": "user",
                    "content": m.input_messages[-1]['content'] if m.input_messages else "",
                    "chunk_type": m.chunk_type.value,
                    "created_at": m.created_at,
                    "dialouge_id": m.dialouge_id
                })
            elif m.chunk_type == ChunkType.AI_MESSAGE:
                messages.append({
                    "role": "assistant",
                    "content": m.output_text,
                    "chunk_type": m.chunk_type.value,
                    "created_at": m.created_at,
                    "dialouge_id": m.dialouge_id
                })
            elif m.chunk_type == ChunkType.MEMORY_RETRIEVE:
                messages.append({
                    "role": "assistant", 
                    "chunk_type": m.chunk_type.value,
                    "memory": m.memory.model_dump() if m.memory else None,
                    "created_at": m.created_at,
                    "dialouge_id": m.dialouge_id
                })
            elif m.chunk_type == ChunkType.MEMORY_EXTRACT:
                messages.append({
                    "role": "assistant",
                    "chunk_type": m.chunk_type.value, 
                    "memory": m.memory.model_dump() if m.memory else None,
                    "created_at": m.created_at,
                    "dialouge_id": m.dialouge_id
                })
        
        logger.info(f"返回 {len(messages)} 条格式化消息")
        return messages

    def _load_recent_messages(self, user_id: str=None, thread_id: str=None) -> str:
        """加载最近的消息"""
        if not user_id or not thread_id:
            return ""
        return self.load_history(user_id, thread_id, limit=self.recent_messages_count)

class LLMResponseProcessor:
    """LLM响应处理器，封装对LLM响应流的处理逻辑"""
    def __init__(self, llm: LiteLLM, model: str, user_id: str=None, thread_id: str=None):
        self.llm = llm
        self.model = model
        self.user_id = user_id
        self.thread_id = thread_id
        self.final_text = ""
        self.final_tool_calls = {}
        self.last_tool_call_id = None
    
    async def process_response(self, messages: List[Dict[str, Any]], **kwargs) -> AsyncGenerator[Tuple[Dict[str, Any], str, Dict[str, Any]], None]:
        """处理LLM响应"""
        logger.info(f"\nchat completion [{self.model}] >>> {messages}")
        
        try:
            resp = await self.llm.acompletion(messages, model=self.model, stream=True, **kwargs)
        except Exception as e:
            logger.error(f"\nchat completion [{self.model}] >>> {messages}\n\nerror >>> {e}")
            return
        
        first_chunk = None
        
        async for chunk in resp:
            ai_output = chunk.choices[0].delta if chunk.choices else None
            
            # 处理文本输出
            if ai_output and ai_output.content:
                if not first_chunk:
                    first_chunk = DialougeChunk(
                        user_id=self.user_id,
                        thread_id=self.thread_id,
                        chunk_type=ChunkType.AI_DELTA,
                        output_text=ai_output.content
                    )
                else:
                    first_chunk.output_text = ai_output.content
                self.final_text += ai_output.content
                # 返回当前块、当前累积的文本和工具调用
                yield first_chunk.model_dump(), self.final_text, self.final_tool_calls
            
            # 处理工具调用
            elif ai_output and ai_output.tool_calls:
                for tool_call in ai_output.tool_calls:
                    tool_id = tool_call.id or self.last_tool_call_id                    
                    if tool_id:
                        self.last_tool_call_id = tool_id
                    if tool_id not in self.final_tool_calls:
                        self.final_tool_calls[tool_id] = ToolCalling(
                            tool_id=tool_id,
                            name="",
                            arguments=""
                        )
                    current = self.final_tool_calls[tool_id]
                    current.name += tool_call.function.name or ""
                    current.arguments += tool_call.function.arguments or ""

class ConversationProcessor:
    """对话处理器，支持工具调用和多轮对话"""
    def __init__(
        self, 
        llm: LiteLLM,
        model: str,
        user_id: str=None,
        thread_id: str=None,
        tool_map: Dict[str, Type[BaseTool]]=None,
        save_chunk_callback=None
    ):
        self.llm = llm
        self.model = model
        self.user_id = user_id
        self.thread_id = thread_id
        self.tool_map = tool_map or {}
        self.save_chunk_callback = save_chunk_callback
        self.max_tool_calls = 10  # 防止无限循环
    
    async def process_conversation(
        self, 
        messages: List[Dict[str, Any]], 
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """处理对话流程，包括工具调用和后续对话"""
        messages = messages.copy()  # 创建消息的副本，避免修改原始消息
        tool_calls_count = 0
        
        # 创建响应处理器
        response_processor = LLMResponseProcessor(
            llm=self.llm,
            model=self.model,
            user_id=self.user_id,
            thread_id=self.thread_id
        )
        
        while True:
            # 获取LLM响应
            final_text = ""
            final_tool_calls = {}
            
            async for chunk, text, tool_calls in response_processor.process_response(messages, **kwargs):
                final_text = text
                final_tool_calls = tool_calls
                yield chunk
            
            # 保存AI消息
            if final_text:
                ai_message = DialougeChunk(
                    user_id=self.user_id,
                    thread_id=self.thread_id,
                    chunk_type=ChunkType.AI_MESSAGE,
                    output_text=final_text
                )
                if self.save_chunk_callback:
                    self.save_chunk_callback(ai_message)
                yield ai_message.model_dump()
            
            # 检查是否有工具调用
            if final_tool_calls and len(final_tool_calls) > 0:
                tool_calls_data = list(final_tool_calls.values())
                
                # 保存工具调用消息
                tool_calls_message = DialougeChunk(
                    user_id=self.user_id,
                    thread_id=self.thread_id,
                    chunk_type=ChunkType.AI_MESSAGE,
                    tool_calls=tool_calls_data
                )
                if self.save_chunk_callback:
                    self.save_chunk_callback(tool_calls_message)
                yield tool_calls_message.model_dump()
                
                # 执行工具调用
                has_tool_results = False
                for tool_call in tool_calls_data:
                    tool_name = tool_call.name
                    tool_arguments = tool_call.arguments
                    
                    if tool_name in self.tool_map:
                        # 执行工具并获取结果
                        tool_result_chunks = []
                        async for chunk in self._execute_tool(
                            tool_id=tool_call.tool_id,
                            tool_class=self.tool_map[tool_name],
                            arguments_json=tool_arguments
                        ):
                            tool_result_chunks.append(chunk.get("output_text", ""))
                            yield chunk
                        
                        # 合并所有结果块为一个完整的工具结果
                        tool_result = "".join(tool_result_chunks)
                        
                        # 将工具结果添加到消息中
                        messages.append({
                            "role": "assistant",
                            "content": final_text,
                            "tool_calls": [{
                                "id": tool_call.tool_id,
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": tool_arguments
                                }
                            }]
                        })
                        
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.tool_id,
                            "name": tool_name,
                            "content": tool_result
                        })
                        
                        has_tool_results = True
                
                # 如果有工具结果，增加计数并继续对话
                if has_tool_results:
                    tool_calls_count += 1
                    if tool_calls_count >= self.max_tool_calls:
                        # 达到最大工具调用次数，结束对话
                        logger.warning(f"已达到最大工具调用次数: {self.max_tool_calls}")
                        break
                    continue  # 继续下一轮对话
            
            # 没有工具调用或工具执行完毕，结束对话
            break
    
    async def _execute_tool(
        self, 
        tool_id: str, 
        tool_class: Type[BaseTool], 
        arguments_json: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """执行工具调用并生成结果块
        
        这是一个异步生成器，会为每个工具执行结果生成一个事件
        """
        try:
            # 解析参数
            arguments = json.loads(arguments_json)
            
            # 执行工具调用
            async for result_chunk in tool_class.call(**arguments):
                # 保存工具执行过程的每个结果块
                tool_result_chunk = DialougeChunk(
                    user_id=self.user_id,
                    thread_id=self.thread_id,
                    chunk_type=ChunkType.TOOL_RESULT,
                    tool_id=tool_id,
                    tool_name=tool_class.name,
                    output_text=result_chunk
                )
                if self.save_chunk_callback:
                    self.save_chunk_callback(tool_result_chunk)
                
                # 生成并返回工具结果块
                yield tool_result_chunk.model_dump()
            
        except Exception as e:
            error_message = f"执行工具 '{tool_class.name}' 失败: {str(e)}"
            logger.error(error_message)
            
            # 创建错误结果块
            error_chunk = DialougeChunk(
                user_id=self.user_id,
                thread_id=self.thread_id,
                chunk_type=ChunkType.TOOL_RESULT,
                tool_id=tool_id,
                tool_name=tool_class.name,
                output_text=error_message
            )
            if self.save_chunk_callback:
                self.save_chunk_callback(error_chunk)
                
            yield error_chunk.model_dump()
