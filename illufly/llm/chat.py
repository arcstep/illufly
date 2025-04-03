from typing import List, Dict, Any, Union, Optional, AsyncGenerator, Tuple, Type
from pydantic import BaseModel, Field

from ..rocksdb import default_rocksdb, IndexedRocksDB
from .base import LiteLLM
from .models import ChunkType, DialougeChunk, ToolCall, MemoryQA
from .memory import Memory, from_messages_to_text
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
        input_created_at = datetime.now().timestamp()
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
        final_tool_calls: Dict[str, ToolCall], 
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
            # 调用LLM生成标题，确保使用await
            title_resp = await self.llm.acompletion(
                messages=title_prompt, 
                model=model, 
                stream=False
            )
            
            # 从acompletion响应中提取标题
            if (hasattr(title_resp, 'choices') and 
                title_resp.choices and 
                hasattr(title_resp.choices[0], 'message') and 
                hasattr(title_resp.choices[0].message, 'content')):
                
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
        """加载历史对话，并确保消息格式与前端预期一致"""
        prefix = DialougeChunk.get_prefix(user_id, thread_id)
        logger.info(f"加载历史对话 - 用户ID: {user_id}, 线程ID: {thread_id}, 前缀: {prefix}, 限制: {limit}")
        
        try:
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
                try:
                    # 构建基本消息结构
                    base_message = {
                        "dialouge_id": m.dialouge_id,
                        "created_at": m.created_at,
                        "chunk_type": m.chunk_type.value
                    }
                    
                    if m.chunk_type == ChunkType.USER_INPUT:
                        # 用户输入消息
                        if not m.input_messages or len(m.input_messages) == 0:
                            logger.warning(f"USER_INPUT没有输入消息: {m}")
                            continue
                            
                        content = ""
                        if m.input_messages and len(m.input_messages) > 0:
                            last_message = m.input_messages[-1]
                            content = last_message.get('content', "")
                            
                        messages.append({
                            **base_message,
                            "role": "user",
                            "content": content
                        })
                        
                    elif m.chunk_type == ChunkType.AI_MESSAGE:
                        # AI消息 - 可能是文本或工具调用
                        content = m.output_text if m.output_text else ""
                        
                        # 检查是否有工具调用
                        if m.tool_calls and len(m.tool_calls) > 0:
                            # 工具调用消息，按前端预期格式处理
                            tool_info = ", ".join([f"{tc.name}" for tc in m.tool_calls])
                            content = f"工具调用: {tool_info}" if not content else content
                        
                        messages.append({
                            **base_message,
                            "role": "assistant",
                            "content": content
                        })
                        
                    elif m.chunk_type == ChunkType.MEMORY_RETRIEVE:
                        # 记忆检索消息 - 需要包含memory对象
                        if not m.memory:
                            logger.warning(f"MEMORY_RETRIEVE没有记忆数据: {m}")
                            continue
                            
                        mem_data = m.memory.model_dump()
                        # 构建符合前端期望的content
                        content = f"记忆: {mem_data.get('topic', '')}/{mem_data.get('question', '')}"
                        
                        messages.append({
                            **base_message,
                            "role": "assistant",
                            "content": content,
                            "memory": mem_data
                        })
                        
                    elif m.chunk_type == ChunkType.MEMORY_EXTRACT:
                        # 记忆提取消息 - 需要包含memory对象
                        if not m.memory:
                            logger.warning(f"MEMORY_EXTRACT没有记忆数据: {m}")
                            continue
                            
                        mem_data = m.memory.model_dump()
                        # 构建符合前端期望的content
                        content = f"提取记忆: {mem_data.get('topic', '')}/{mem_data.get('question', '')}"
                        
                        messages.append({
                            **base_message,
                            "role": "assistant",
                            "content": content,
                            "memory": mem_data
                        })
                        
                    elif m.chunk_type == ChunkType.TOOL_RESULT:
                        # 工具结果消息
                        content = m.output_text if m.output_text else ""
                        tool_name = m.tool_name if m.tool_name else "未知工具"
                        
                        messages.append({
                            **base_message,
                            "role": "tool",
                            "name": tool_name,
                            "tool_call_id": m.tool_id,
                            "content": content
                        })
                        
                    elif m.chunk_type == ChunkType.TITLE_UPDATE:
                        # 标题更新通知消息
                        content = m.output_text if m.output_text else ""
                        messages.append({
                            **base_message,
                            "role": "system", 
                            "content": content
                        })
                        
                except Exception as e:
                    logger.error(f"处理历史消息错误: {e}, 消息: {m}")
                    continue
            
            # 按时间顺序排序消息
            messages.sort(key=lambda x: x.get("created_at", 0))
            logger.info(f"返回 {len(messages)} 条格式化消息")
            return messages
            
        except Exception as e:
            logger.error(f"加载历史对话失败: {e}")
            return []

    def _load_recent_messages(self, user_id: str=None, thread_id: str=None) -> List[Dict[str, Any]]:
        """加载最近的消息"""
        if not user_id or not thread_id:
            logger.info("用户ID或线程ID为空，返回空历史消息")
            return []
        return self.load_history(user_id, thread_id, limit=self.recent_messages_count)

    async def _retrieve_memory(
        self, 
        user_id: str, 
        input_text: str, 
        k: int = 5
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """检索记忆
        
        从记忆中检索与输入文本相关的内容
        
        Args:
            user_id: 用户ID
            input_text: 查询文本
            k: 返回记忆数量
            
        Yields:
            包含记忆信息的消息块
        """
        if not self.memory:
            return
        
        memory_results = await self.memory.retrieve(
            user_id=user_id,
            query=input_text,
            k=k
        )
        
        if not memory_results:
            return
        
        # 对每个记忆结果生成一个块
        for memory in memory_results:
            memory_text = f"主题: {memory.topic}\n问题: {memory.question}\n回答: {memory.answer}"
            memory_retrieve_chunk = DialougeChunk(
                user_id=user_id,
                chunk_type=ChunkType.MEMORY_RETRIEVE,
                output_text=memory_text,
                memory=memory
            )
            
            # 保存记忆检索块
            self.save_dialog_chunk(memory_retrieve_chunk)
            
            # 生成前端期望的格式
            memory_data = {
                "role": "assistant",
                "content": memory_text,
                "chunk_type": ChunkType.MEMORY_RETRIEVE.value,
                "created_at": memory_retrieve_chunk.created_at,
                "dialouge_id": memory_retrieve_chunk.dialouge_id,
                "memory": memory.model_dump()
            }
            
            yield memory_data
    
    async def _extract_memory(
        self, 
        user_id: str, 
        messages: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """从对话中提取记忆
        
        将对话转换为记忆并存储
        
        Args:
            user_id: 用户ID
            messages: 消息列表
            
        Returns:
            包含记忆信息的消息块，如果没有提取到记忆则返回None
        """
        if not self.memory or not messages:
            return None
        
        # 将消息转换为文本
        text = from_messages_to_text(messages)
        
        # 提取记忆
        memory = await self.memory.extract(
            user_id=user_id,
            text=text
        )
        
        if not memory:
            return None
        
        # 创建记忆提取块
        memory_text = f"我记住了:\n主题: {memory.topic}\n问题: {memory.question}\n回答: {memory.answer}"
        memory_extract_chunk = DialougeChunk(
            user_id=user_id,
            chunk_type=ChunkType.MEMORY_EXTRACT,
            output_text=memory_text,
            memory=memory
        )
        
        # 保存记忆提取块
        self.save_dialog_chunk(memory_extract_chunk)
        
        # 生成前端期望的格式
        memory_data = {
            "role": "assistant",
            "content": memory_text,
            "chunk_type": ChunkType.MEMORY_EXTRACT.value,
            "created_at": memory_extract_chunk.created_at,
            "dialouge_id": memory_extract_chunk.dialouge_id,
            "memory": memory.model_dump()
        }
        
        return memory_data

class LLMResponseProcessor:
    """LLM响应处理器，将LLM响应处理为增量块和工具调用"""
    def __init__(
        self, 
        llm: LiteLLM,
        model: str,
        user_id: str=None,
        thread_id: str=None,
        save_chunk_callback=None
    ):
        self.llm = llm
        self.model = model
        self.user_id = user_id 
        self.thread_id = thread_id
        self.save_chunk_callback = save_chunk_callback
    
    async def process_response(
        self, 
        messages: List[Dict[str, Any]], 
        stream: bool = True,
        **kwargs
    ) -> AsyncGenerator[Tuple[Dict[str, Any], str, Dict[str, ToolCall]], None]:
        """处理LLM响应
        
        Args:
            messages: 消息列表
            stream: 是否使用流式响应
            
        Yields:
            chunk: 增量消息块
            text: 到目前为止累积的文本
            tool_calls: 到目前为止累积的工具调用
        """
        # 对于流式响应
        if stream:
            text_buffer = ""
            tool_calls = {}  # 使用字典存储工具调用，以工具ID为键
            
            # 先获取协程
            response_coroutine = self.llm.acompletion(
                messages=messages,
                model=self.model,
                stream=True,
                **kwargs
            )
            
            # 先await协程获取响应对象
            response = await response_coroutine
            
            # 然后使用async for迭代结果
            async for chunk in response:
                # 处理acompletion返回的格式
                ai_output = chunk.choices[0].delta if hasattr(chunk, 'choices') else None
                
                # 处理文本内容
                content = ""
                if ai_output and hasattr(ai_output, 'content') and ai_output.content:
                    content = ai_output.content
                
                # 用于检查是否有工具调用的标志
                has_tool_calls = False
                
                # 处理工具调用
                if ai_output and hasattr(ai_output, 'tool_calls') and ai_output.tool_calls:
                    has_tool_calls = True
                    for tc in ai_output.tool_calls:
                        tc_id = tc.id
                        tc_func = tc.function
                        
                        # 如果是新的工具调用，初始化工具调用对象
                        if tc_id and tc_id not in tool_calls:
                            tool_calls[tc_id] = ToolCall(
                                tool_id=tc_id,
                                name=tc_func.name or "",
                                arguments=""
                            )
                        
                        # 如果工具调用已存在，更新其参数
                        if tc_id and tc_id in tool_calls:
                            if hasattr(tc_func, 'name') and tc_func.name:
                                tool_calls[tc_id].name = tc_func.name
                            
                            if hasattr(tc_func, 'arguments') and tc_func.arguments:
                                tool_calls[tc_id].arguments += tc_func.arguments
                
                # 只有当有内容或工具调用时才创建增量块
                if content or has_tool_calls:
                    # 更新文本缓冲区
                    if content:
                        text_buffer += content
                    
                    # 创建增量块
                    delta_chunk = DialougeChunk(
                        user_id=self.user_id,
                        thread_id=self.thread_id,
                        chunk_type=ChunkType.AI_DELTA,
                        output_text=content
                    )
                    
                    # 保存增量块
                    if self.save_chunk_callback:
                        self.save_chunk_callback(delta_chunk)
                    
                    # 生成前端期望的格式
                    chunk_data = {
                        "role": "assistant",
                        "content": content,
                        "chunk_type": ChunkType.AI_DELTA.value,
                        "created_at": delta_chunk.created_at,
                        "dialouge_id": delta_chunk.dialouge_id
                    }
                    
                    # 只有在实际有内容或工具调用时才yield结果
                    yield chunk_data, text_buffer, tool_calls
        
        # 对于非流式响应
        else:
            response = await self.llm.acompletion(
                messages=messages,
                model=self.model,
                stream=False,
                **kwargs
            )
            
            # 处理acompletion返回的格式
            content = ""
            tool_calls = {}
            
            if hasattr(response, 'choices') and response.choices:
                ai_output = response.choices[0].message
                
                # 获取内容
                if hasattr(ai_output, 'content') and ai_output.content:
                    content = ai_output.content
                
                # 获取工具调用
                if hasattr(ai_output, 'tool_calls') and ai_output.tool_calls:
                    for tc in ai_output.tool_calls:
                        tc_id = tc.id
                        tc_func = tc.function
                        
                        tool_calls[tc_id] = ToolCall(
                            tool_id=tc_id,
                            name=tc_func.name if hasattr(tc_func, 'name') else "",
                            arguments=tc_func.arguments if hasattr(tc_func, 'arguments') else ""
                        )
            
            # 创建消息块
            chunk = DialougeChunk(
                user_id=self.user_id,
                thread_id=self.thread_id,
                chunk_type=ChunkType.AI_MESSAGE,
                output_text=content
            )
            
            # 保存消息块
            if self.save_chunk_callback:
                self.save_chunk_callback(chunk)
            
            # 生成前端期望的格式
            chunk_data = {
                "role": "assistant",
                "content": content,
                "chunk_type": ChunkType.AI_MESSAGE.value,
                "created_at": chunk.created_at,
                "dialouge_id": chunk.dialouge_id
            }
            
            yield chunk_data, content, tool_calls

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
                
                # 生成前端期望的格式
                message_data = {
                    "role": "assistant",
                    "content": final_text,
                    "chunk_type": ChunkType.AI_MESSAGE.value,
                    "created_at": ai_message.created_at,
                    "dialouge_id": ai_message.dialouge_id
                }
                yield message_data
            
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
                
                # 工具调用总结为文本形式展示
                tool_names = ", ".join([tc.name for tc in tool_calls_data])
                message_data = {
                    "role": "assistant",
                    "content": f"工具调用: {tool_names}",
                    "chunk_type": ChunkType.AI_MESSAGE.value,
                    "created_at": tool_calls_message.created_at,
                    "dialouge_id": tool_calls_message.dialouge_id,
                    "tool_calls": [tc.model_dump() for tc in tool_calls_data]
                }
                yield message_data
                
                # 执行工具调用
                has_tool_results = False
                for tool_call in tool_calls_data:
                    tool_name = tool_call.name
                    tool_arguments = tool_call.arguments
                    
                    if tool_name in self.tool_map:
                        # 收集工具执行过程中的所有结果
                        tool_result_text = ""
                        async for result_chunk in self._execute_tool(
                            tool_id=tool_call.tool_id,
                            tool_class=self.tool_map[tool_name],
                            arguments_json=tool_arguments
                        ):
                            # 如果每个结果块都需要传给前端展示，则yield
                            yield result_chunk
                            # 累积结果文本
                            if 'output_text' in result_chunk:
                                tool_result_text += result_chunk['output_text']
                        
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
                            "content": tool_result_text
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
                
                # 生成前端期望的格式
                chunk_data = {
                    "role": "tool",
                    "name": tool_class.name,
                    "tool_call_id": tool_id,
                    "content": result_chunk,
                    "chunk_type": ChunkType.TOOL_RESULT.value,
                    "created_at": tool_result_chunk.created_at,
                    "dialouge_id": tool_result_chunk.dialouge_id,
                    "output_text": result_chunk  # 额外字段，与DialougeChunk保持一致
                }
                
                # 生成并返回工具结果块
                yield chunk_data
            
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
            
            # 生成前端期望的格式
            error_data = {
                "role": "tool",
                "name": tool_class.name,
                "tool_call_id": tool_id,
                "content": error_message,
                "chunk_type": ChunkType.TOOL_RESULT.value,
                "created_at": error_chunk.created_at,
                "dialouge_id": error_chunk.dialouge_id,
                "output_text": error_message
            }
            
            yield error_data
