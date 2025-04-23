from typing import List, Dict, Any, Union, Optional, AsyncGenerator, Tuple, Type
from pydantic import BaseModel, Field

from voidring import default_rocksdb, IndexedRocksDB
from ..llm.litellm import LiteLLM
from ..llm.retriever import ChromaRetriever
from ..llm.base_tool import BaseTool
from .memory import Memory, from_messages_to_text
from .thread import ThreadManager
from .schemas import ChunkType, DialogueChunk, Dialogue, Thread, ToolCall, MemoryQA

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

        self.recent_dialogues_count = 5
        
        # 注册数据模型到数据库
        DialogueChunk.register_indexes(self.db)
        Dialogue.register_indexes(self.db)
        Thread.register_indexes(self.db)

    def register_tool(self, tool_class: Type[BaseTool]) -> None:
        """注册工具到对话智能体"""
        if tool_class.name in self.tool_map:
            logger.warning(f"工具 '{tool_class.name}' 已存在，将被覆盖")
        
        self.tools.append(tool_class)
        self.tool_map[tool_class.name] = tool_class
        logger.info(f"已注册工具: {tool_class.name}")
        
    def _create_new_dialogue(self, user_id: str, thread_id: str, user_content: str = "") -> Dialogue:
        """创建新的对话轮次"""
        # 获取当前线程
        thread_key = Thread.get_key(user_id, thread_id)
        thread = self.db.get_as_model(Thread.__name__, thread_key)
        
        if not thread:
            # 如果线程不存在，创建新线程
            thread = Thread(
                user_id=user_id,
                thread_id=thread_id,
                dialogue_count=0
            )
            self.db.update_with_indexes(
                collection_name=Thread.__name__,
                key=thread_key,
                value=thread
            )
        
        # 增加对话轮次计数
        thread.dialogue_count += 1
        self.db.update_with_indexes(
            collection_name=Thread.__name__,
            key=thread_key,
            value=thread
        )
        
        # 创建新的对话轮次
        dialogue = Dialogue(
            user_id=user_id,
            thread_id=thread_id,
            user_content=user_content,
            chunk_count=0
        )
        
        dialogue_key = Dialogue.get_key(user_id, thread_id, dialogue.dialogue_id)
        self.db.update_with_indexes(
            collection_name=Dialogue.__name__,
            key=dialogue_key,
            value=dialogue
        )
        
        return dialogue
    
    def _update_dialogue(self, dialogue: Dialogue, ai_content: str = "", completed: bool = False) -> Dialogue:
        """更新对话轮次"""
        dialogue.ai_content = ai_content
        dialogue.updated_at = datetime.now().timestamp()
        dialogue.completed = completed
        
        dialogue_key = Dialogue.get_key(dialogue.user_id, dialogue.thread_id, dialogue.dialogue_id)
        self.db.update_with_indexes(
            collection_name=Dialogue.__name__,
            key=dialogue_key,
            value=dialogue
        )
        
        return dialogue
    
    def save_dialogue_chunk(self, chunk: DialogueChunk) -> None:
        """保存对话块

        同时更新对话轮次的chunk_count
        """
        if not (chunk.user_id and chunk.thread_id and chunk.dialogue_id):
            logger.warning(f"对话块缺少必要字段，无法保存: {chunk}")
            return
        
        # 保存对话块
        chunk_key = DialogueChunk.get_key(
            chunk.user_id, 
            chunk.thread_id, 
            chunk.dialogue_id, 
            chunk.chunk_id
        )
        self.db.update_with_indexes(
            collection_name=DialogueChunk.__name__,
            key=chunk_key,
            value=chunk
        )
        
        # 更新对话轮次的chunk_count
        dialogue_key = Dialogue.get_key(chunk.user_id, chunk.thread_id, chunk.dialogue_id)
        dialogue = self.db.get_as_model(Dialogue.__name__, dialogue_key)
        if dialogue:
            dialogue.chunk_count += 1
            self.db.update_with_indexes(
                collection_name=Dialogue.__name__,
                key=dialogue_key,
                value=dialogue
            )
        
        logger.info(f"已保存对话块: {chunk_key}")
    
    def _load_recent_dialogues(self, user_id: str, thread_id: str) -> List[Dialogue]:
        """加载最近的对话轮次"""
        if not user_id or not thread_id:
            return []

        dialogues = Dialogue.all_dialogues(self.db, user_id, thread_id, limit=100)
        # 按时间倒序，取最近的几轮
        if dialogues:
            dialogues.reverse()
            dialogues = dialogues[:self.recent_dialogues_count]
            dialogues.reverse()  # 恢复时间正序
        
        return dialogues
        
    def _load_dialogue_chunks(self, user_id: str, thread_id: str, dialogue_id: str) -> List[DialogueChunk]:
        """加载对话轮次的所有对话块"""
        if not user_id or not thread_id or not dialogue_id:
            return []
        
        return DialogueChunk.all_chunks(self.db, user_id, thread_id, dialogue_id, limit=100)

    async def chat(self, messages: List[Dict[str, Any]], model: str, user_id: str=None, thread_id: str=None, **kwargs):
        """对话主流程
        
        协调各个处理模块，完成完整的对话流程：
        1. 创建新对话轮次
        2. 加载历史 + 检索记忆
        3. 注入记忆 + 保存用户输入
        4. 并行执行：提取新记忆 + 对话补全
        """
        if not messages:
            raise ValueError("messages 不能为空")
        raw_messages = [*messages] if isinstance(messages, list) else messages

        # 标准化用户输入并提取用户最新消息
        input_created_at = datetime.now().timestamp()
        messages = self._normalize_input_messages(messages)
        user_content = messages[-1].get('content', '') if messages[-1].get('role') == 'user' else ''
        
        # 1. 创建新对话轮次
        dialogue = self._create_new_dialogue(user_id, thread_id, user_content)
        dialogue_id = dialogue.dialogue_id
        
        # 2. 加载历史消息
        history_messages = self.load_history(user_id, thread_id)
        is_first_conversation = len(history_messages) == 0
        
        messages = self._merge_messages(messages, history_messages)
        
        # 3. 检索记忆
        retrieved_memories = await self.memory.retrieve(messages, user_id)
        
        # 4. 发送检索到的记忆
        if retrieved_memories:
            memory_chunks = await self._process_retrieved_memories(retrieved_memories, user_id, thread_id, dialogue_id)
            for chunk in memory_chunks:
                yield chunk
        
        # 5. 注入记忆到提示中
        messages, memory_table = self._inject_memory(messages, retrieved_memories)
        
        # 6. 保存用户输入
        await self._save_user_input(raw_messages, messages, user_id, thread_id, dialogue_id, input_created_at)
        
        # 7. 并行执行记忆提取和对话补全
        extract_task = asyncio.create_task(
            self.memory.extract(messages, model, memory_table, user_id)
        )
        
        # 8. 创建LLM配置并添加工具
        llm_kwargs = kwargs.copy()
        if self.tools and not llm_kwargs.get("tools"):
            llm_kwargs["tools"] = [tool.to_openai() for tool in self.tools]
        
        # 9. 执行对话流程 (可能包括多轮工具调用)
        final_text = ""
        final_tool_calls = {}
        
        conversation_processor = ConversationProcessor(
            llm=self.llm,
            model=model,
            user_id=user_id,
            thread_id=thread_id,
            dialogue_id=dialogue_id,
            tool_map=self.tool_map,
            save_chunk_callback=self.save_dialogue_chunk
        )
        
        # 开始对话处理，可能包含多轮工具调用
        async for chunk in conversation_processor.process_conversation(messages, **llm_kwargs):
            # 记录最终的文本和工具调用结果
            if isinstance(chunk, dict):
                if chunk.get("chunk_type") == ChunkType.AI_MESSAGE.value:
                    final_text += chunk.get("content", "")
                    if chunk.get("tool_calls"):
                        final_tool_calls = {tc["tool_id"]: tc for tc in chunk.get("tool_calls", [])}
            
            # 将处理后的数据传递给调用者
            yield chunk
        
        # 10. 更新对话轮次状态
        self._save_ai_output(final_text, final_tool_calls, user_id, thread_id)
        self._update_dialogue(dialogue, ai_content=final_text, completed=True)
        
        # 11. 等待记忆提取完成并处理结果
        logger.info("等待记忆提取完成...")
        extracted_memories = await extract_task
        if extracted_memories:
            logger.info(f"成功提取记忆 {len(extracted_memories)} 条，准备推送到前端")
            try:
                async for chunk in self._process_extracted_memories(extracted_memories, user_id, thread_id, dialogue_id):
                    logger.info(f"推送记忆到前端: {chunk.get('content', '')[:30]}...")
                    yield chunk
            except Exception as e:
                logger.error(f"推送记忆到前端失败: {e}")
        else:
            logger.info("没有提取到新记忆")
        
        # 12. 如果是首轮对话，生成标题
        if is_first_conversation and user_id and thread_id and final_text:
            logger.info(f"首轮对话，准备生成标题 (user_id: {user_id}, thread_id: {thread_id})")
            try:
                title_generator = self._generate_title(messages, final_text, model, user_id, thread_id, dialogue_id)
                async for title_chunk in title_generator:
                    logger.info(f"推送标题到前端: {title_chunk.get('content', '')}")
                    yield title_chunk
            except Exception as e:
                logger.error(f"生成或推送标题失败: {e}")

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
        return self.load_history(user_id, thread_id)
    
    def _merge_messages(self, messages: List[Dict[str, Any]], history_messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """合并当前消息和历史消息"""
        if not messages:
            return history_messages
            
        if messages[0].get("role", None) == "system":
            return [messages[0], *history_messages, *messages[1:]]
        else:
            return [*history_messages, *messages]
    
    async def _process_retrieved_memories(
        self,
        retrieved_memories: List[MemoryQA],
        user_id: str=None,
        thread_id: str=None,
        dialogue_id: str=None
    ) -> List[Dict[str, Any]]:
        """处理检索到的记忆，将其保存并准备发送"""
        memory_chunks = []
        sequence = 0
        
        for memory in retrieved_memories:
            memory_chunk = DialogueChunk(
                user_id=user_id,
                thread_id=thread_id,
                dialogue_id=dialogue_id,
                chunk_type=ChunkType.MEMORY_RETRIEVE,
                role="assistant",
                sequence=sequence,
                memory=memory,
                is_final=True
            )
            self.save_dialogue_chunk(memory_chunk)
            memory_chunks.append(memory_chunk.model_dump())
            sequence += 1
            
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
        raw_messages: List[Dict[str, Any]], 
        messages: List[Dict[str, Any]], 
        user_id: str=None, 
        thread_id: str=None,
        dialogue_id: str=None,
        created_at: float=None
    ) -> None:
        """保存用户输入"""
        dialog_chunk = DialogueChunk(
            user_id=user_id,
            thread_id=thread_id,
            dialogue_id=dialogue_id,
            chunk_type=ChunkType.USER_INPUT,
            role="user",
            input_messages=raw_messages,
            patched_messages=messages,
            is_final=True,
            created_at=created_at or datetime.now().timestamp()
        )
        self.save_dialogue_chunk(dialog_chunk)
    
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
            dialogue_chunk = DialogueChunk(
                user_id=user_id,
                thread_id=thread_id,
                chunk_type=ChunkType.AI_MESSAGE,
                output_text=final_text
            )
            self.save_dialogue_chunk(dialogue_chunk)
        
        # 保存工具调用
        if final_tool_calls:
            dialogue_chunk = DialogueChunk(
                user_id=user_id,
                thread_id=thread_id,
                chunk_type=ChunkType.AI_MESSAGE,
                tool_calls=list(final_tool_calls.values())
            )
            self.save_dialogue_chunk(dialogue_chunk)
            yield dialogue_chunk.model_dump()
    
    async def _process_extracted_memories(
        self, 
        extracted_memories: List[MemoryQA], 
        user_id: str=None, 
        thread_id: str=None,
        dialogue_id: str=None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """处理提取的记忆"""
        if not extracted_memories:
            logger.info("没有提取到记忆")
            return
        
        logger.info(f"处理提取的记忆: {len(extracted_memories)} 条")
        sequence = 0
            
        for memory in extracted_memories:
            memory_chunk = DialogueChunk(
                user_id=user_id,
                thread_id=thread_id,
                dialogue_id=dialogue_id,
                chunk_type=ChunkType.MEMORY_EXTRACT,
                role="assistant",
                sequence=sequence,
                memory=memory,
                is_final=True
            )
            # 保存到数据库
            self.save_dialogue_chunk(memory_chunk)
            
            # 使用统一的model_dump方法获取格式化的消息
            formatted_message = memory_chunk.model_dump()
            logger.info(f"记忆提取成功: {formatted_message.get('content', '')}")
            
            # 将格式化的消息发送到前端
            yield formatted_message
            sequence += 1
    
    async def _generate_title(
        self, 
        messages: List[Dict[str, Any]], 
        final_text: str, 
        model: str, 
        user_id: str=None, 
        thread_id: str=None,
        dialogue_id: str=None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """为首轮对话生成标题"""
        # 构建生成标题的提示
        user_content = messages[-1].get("content", "") if messages else ""
        logger.info(f"开始生成标题，用户ID: {user_id}, 线程ID: {thread_id}")
        logger.info(f"标题生成输入 - 用户消息: {user_content[:50]}..., AI回复: {final_text[:50]}...")
        
        title_prompt = [
            {"role": "system", "content": "你是一个对话标题生成助手。请根据用户的消息和AI的回复，提炼出一个简短、准确的对话标题，不超过15个字。只需返回标题本身，不要包含任何其他文字或标点。"},
            {"role": "user", "content": f"用户消息：{user_content}\nAI回复：{final_text}\n请生成一个简短的对话标题："}
        ]
        
        try:
            # 调用LLM生成标题，确保使用await
            logger.info(f"调用LLM生成标题，模型: {model}")
            title_resp = await self.llm.acompletion(
                messages=title_prompt, 
                # model=model, 
                stream=False
            )
            
            logger.info(f"收到标题生成响应: {title_resp}")
            
            # 从acompletion响应中提取标题
            if (hasattr(title_resp, 'choices') and 
                title_resp.choices and 
                hasattr(title_resp.choices[0], 'message') and 
                hasattr(title_resp.choices[0].message, 'content')):
                
                title = title_resp.choices[0].message.content.strip()
                logger.info(f"从响应中提取到标题: '{title}'")
                
                # 限制标题长度
                if len(title) > 20:
                    title = title[:20]
                    logger.info(f"标题长度超过20，截断为: '{title}'")
                
                # 更新Thread的标题
                logger.info(f"更新线程标题: user_id={user_id}, thread_id={thread_id}, title='{title}'")
                updated_thread = self.thread_manager.update_thread_title(user_id, thread_id, title)
                
                if updated_thread:
                    logger.info(f"线程标题更新成功: {updated_thread}")
                    # 创建标题更新通知
                    title_chunk = DialogueChunk(
                        user_id=user_id,
                        thread_id=thread_id,
                        dialogue_id=dialogue_id,
                        chunk_type=ChunkType.TITLE_UPDATE,
                        role="system",
                        output_text=title,
                        is_final=True
                    )
                    # 保存到数据库
                    self.save_dialogue_chunk(title_chunk)
                    logger.info(f"已保存标题更新通知到数据库")
                    
                    # 使用统一的model_dump方法获取格式化的消息
                    formatted_message = title_chunk.model_dump()
                    logger.info(f"标题生成成功: '{title}'，准备推送到前端")
                    
                    # 将格式化的消息发送到前端
                    yield formatted_message
                else:
                    logger.warning(f"线程标题更新失败，生成的标题为: '{title}'")
            else:
                logger.error(f"无法从响应中提取标题: {title_resp}")
        except Exception as e:
            logger.error(f"生成标题过程中发生错误: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            # 标题生成失败不影响正常对话流程，可以静默失败

    def save_dialogue_chunk(self, chunk: DialogueChunk):
        """保存对话片段

        仅当用户ID和线程ID存在时，才保存对话片段
        """
        if chunk.user_id and chunk.thread_id:
            key = DialogueChunk.get_key(chunk.user_id, chunk.thread_id, chunk.dialogue_id, chunk.chunk_id)
            logger.info(f"\nsave_dialogue_chunk >>> key: {key}, chunk: {chunk}")
            self.db.update_with_indexes(
                collection_name=DialogueChunk.__name__,
                key=key,
                value=chunk
            )

    def load_history(self, user_id: str, thread_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """加载历史对话，并确保消息格式与前端预期一致
        
        流程：
        1. 获取最近的对话轮次
        2. 对于每个对话轮次，加载其用户输入和AI回复
        3. 按时间排序返回处理后的消息
        """
        if not user_id or not thread_id:
            return []
            
        try:
            # 加载最近的对话轮次
            recent_dialogues = self._load_recent_dialogues(user_id, thread_id)
            if not recent_dialogues:
                logger.info("没有找到历史对话轮次")
                return []
                
            logger.info(f"找到 {len(recent_dialogues)} 轮历史对话")
            
            # 收集所有需要处理的对话轮次和块
            messages = []
            
            # 对每个对话轮次，加载并处理其对话块
            for dialogue in recent_dialogues:
                try:
                    dialogue_chunks = self._load_dialogue_chunks(
                        user_id,
                        thread_id,
                        dialogue.dialogue_id
                    )
                    
                    if not dialogue_chunks:
                        logger.warning(f"对话轮次 {dialogue.dialogue_id} 没有对话块")
                        continue
                    
                    # 过滤并处理对话块，只保留最终版本和非增量块
                    processed_chunks = []
                    for chunk in dialogue_chunks:
                        # 跳过AI增量块
                        if chunk.chunk_type == ChunkType.AI_DELTA:
                            continue
                        
                        # 其他类型块直接使用model_dump
                        processed_chunks.append(chunk.model_dump())
                    
                    # 将处理后的块添加到消息列表
                    messages.extend(processed_chunks)
                    
                except Exception as e:
                    logger.error(f"处理对话轮次 {dialogue.dialogue_id} 时出错: {e}")
                    continue
            
            # 按时间排序
            messages.sort(key=lambda x: x.get("created_at", 0))
            
            logger.info(f"返回 {len(messages)} 条格式化历史消息")
            return messages
            
        except Exception as e:
            logger.error(f"加载历史对话失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

class LLMResponseProcessor:
    """LLM响应处理器，将LLM响应处理为增量块和工具调用"""
    def __init__(
        self, 
        llm: LiteLLM,
        model: str,
        user_id: str=None,
        thread_id: str=None,
        dialogue_id: str=None,
        save_chunk_callback=None
    ):
        self.llm = llm
        self.model = model
        self.user_id = user_id 
        self.thread_id = thread_id
        self.dialogue_id = dialogue_id
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
            sequence = 0  # 增量消息序列号
            chunk_id = None  # 用于存储第一个增量消息的chunk_id
            
            # 先获取协程
            response_coroutine = self.llm.acompletion(
                messages=messages,
                # model=self.model,
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
                    
                    # 创建增量块，重用相同的chunk_id
                    is_first_chunk = chunk_id is None
                    
                    # 创建对话块参数
                    chunk_params = {
                        "user_id": self.user_id,
                        "thread_id": self.thread_id,
                        "dialogue_id": self.dialogue_id,
                        "chunk_type": ChunkType.AI_DELTA,
                        "role": "assistant",
                        "output_text": content,
                        "sequence": sequence,
                        "is_final": False
                    }
                    
                    # 如果不是第一个块，添加chunk_id参数
                    if not is_first_chunk:
                        chunk_params["chunk_id"] = chunk_id
                    
                    # 创建增量块
                    delta_chunk = DialogueChunk(**chunk_params)
                    
                    # 保存第一个增量块的chunk_id，后续复用
                    if is_first_chunk:
                        chunk_id = delta_chunk.chunk_id
                    
                    # 保存增量块
                    if self.save_chunk_callback:
                        self.save_chunk_callback(delta_chunk)
                    
                    # 使用model_dump获取标准化的消息格式
                    chunk_data = delta_chunk.model_dump()
                    
                    # 只有在实际有内容或工具调用时才yield结果
                    yield chunk_data, text_buffer, tool_calls
                    sequence += 1
        
        # 对于非流式响应
        else:
            response = await self.llm.acompletion(
                messages=messages,
                # model=self.model,
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
            chunk = DialogueChunk(
                user_id=self.user_id,
                thread_id=self.thread_id,
                dialogue_id=self.dialogue_id,
                chunk_type=ChunkType.AI_MESSAGE,
                role="assistant",
                output_text=content,
                is_final=True,
                sequence=0
            )
            
            # 保存消息块
            if self.save_chunk_callback:
                self.save_chunk_callback(chunk)
            
            # 使用model_dump获取标准化的消息格式
            chunk_data = chunk.model_dump()
            
            yield chunk_data, content, tool_calls

class ConversationProcessor:
    """对话处理器，支持工具调用和多轮对话"""
    def __init__(
        self, 
        llm: LiteLLM,
        model: str,
        user_id: str=None,
        thread_id: str=None,
        dialogue_id: str=None,
        tool_map: Dict[str, Type[BaseTool]]=None,
        save_chunk_callback=None
    ):
        self.llm = llm
        self.model = model
        self.user_id = user_id
        self.thread_id = thread_id
        self.dialogue_id = dialogue_id
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
            thread_id=self.thread_id,
            dialogue_id=self.dialogue_id,
            save_chunk_callback=self.save_chunk_callback
        )
        
        while True:
            # 获取LLM响应
            final_text = ""
            final_tool_calls = {}
            first_chunk_id = None  # 用于存储第一个增量消息的chunk_id
            
            async for chunk, text, tool_calls in response_processor.process_response(messages, **kwargs):
                final_text = text
                final_tool_calls = tool_calls
                
                # 记录第一个增量消息的chunk_id
                if first_chunk_id is None and chunk.get("chunk_type") == ChunkType.AI_DELTA.value:
                    first_chunk_id = chunk.get("chunk_id")
                    
                yield chunk
            
            # 保存AI消息，使用与增量消息相同的chunk_id
            if final_text:
                # 创建对话块参数
                ai_message_params = {
                    "user_id": self.user_id,
                    "thread_id": self.thread_id,
                    "dialogue_id": self.dialogue_id,
                    "chunk_type": ChunkType.AI_MESSAGE,
                    "role": "assistant",
                    "output_text": final_text,
                    "is_final": True
                }
                
                # 如果有first_chunk_id，添加到参数中
                if first_chunk_id:
                    ai_message_params["chunk_id"] = first_chunk_id
                
                # 创建AI消息块
                ai_message = DialogueChunk(**ai_message_params)
                
                if self.save_chunk_callback:
                    self.save_chunk_callback(ai_message)
                
                # 使用model_dump获取标准化的消息格式
                message_data = ai_message.model_dump()
                yield message_data
            
            # 检查是否有工具调用
            if final_tool_calls and len(final_tool_calls) > 0:
                tool_calls_data = list(final_tool_calls.values())
                
                # 创建对话块参数
                tool_calls_params = {
                    "user_id": self.user_id,
                    "thread_id": self.thread_id,
                    "dialogue_id": self.dialogue_id,
                    "chunk_type": ChunkType.AI_MESSAGE,
                    "role": "assistant",
                    "tool_calls": tool_calls_data,
                    "is_final": True
                }
                
                # 如果有first_chunk_id，添加到参数中
                if first_chunk_id:
                    tool_calls_params["chunk_id"] = first_chunk_id
                
                # 创建工具调用消息块
                tool_calls_message = DialogueChunk(**tool_calls_params)
                
                if self.save_chunk_callback:
                    self.save_chunk_callback(tool_calls_message)
                
                # 使用model_dump获取标准化的消息格式
                message_data = tool_calls_message.model_dump()
                yield message_data
                
                # 执行工具调用
                has_tool_results = False
                tool_sequence = 0
                
                for tool_call in tool_calls_data:
                    tool_name = tool_call.name
                    tool_arguments = tool_call.arguments
                    
                    if tool_name in self.tool_map:
                        # 收集工具执行过程中的所有结果
                        tool_result_text = ""
                        async for result_chunk in self._execute_tool(
                            tool_id=tool_call.tool_id,
                            tool_class=self.tool_map[tool_name],
                            arguments_json=tool_arguments,
                            sequence=tool_sequence
                        ):
                            # 如果每个结果块都需要传给前端展示，则yield
                            yield result_chunk
                            # 累积结果文本
                            if 'output_text' in result_chunk:
                                tool_result_text += result_chunk['output_text']
                            
                            tool_sequence += 1
                        
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
        arguments_json: str,
        sequence: int = 0
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """执行工具调用并生成结果块
        
        这是一个异步生成器，会为每个工具执行结果生成一个事件
        """
        try:
            # 解析参数
            arguments = json.loads(arguments_json)
            
            # 执行工具调用
            tool_chunk_id = None  # 用于存储第一个工具结果块的ID
            local_sequence = sequence  # 局部序列号
            
            async for result_chunk in tool_class.call(**arguments):
                # 创建工具结果块
                is_first_chunk = tool_chunk_id is None
                
                # 创建对话块参数
                chunk_params = {
                    "user_id": self.user_id,
                    "thread_id": self.thread_id,
                    "dialogue_id": self.dialogue_id,
                    "chunk_type": ChunkType.TOOL_RESULT,
                    "role": "tool",
                    "tool_id": tool_id,
                    "tool_name": tool_class.name,
                    "output_text": result_chunk,
                    "sequence": local_sequence,
                    "is_final": True
                }
                
                # 如果不是第一个块，添加chunk_id参数
                if not is_first_chunk:
                    chunk_params["chunk_id"] = tool_chunk_id
                
                # 创建增量块
                tool_result_chunk = DialogueChunk(**chunk_params)
                
                # 保存第一个工具结果块的ID
                if is_first_chunk:
                    tool_chunk_id = tool_result_chunk.chunk_id
                
                # 保存工具结果块
                if self.save_chunk_callback:
                    self.save_chunk_callback(tool_result_chunk)
                
                # 使用model_dump获取标准化的格式
                chunk_data = tool_result_chunk.model_dump()
                
                # 生成并返回工具结果块
                yield chunk_data
                local_sequence += 1
            
        except Exception as e:
            error_message = f"执行工具 '{tool_class.name}' 失败: {str(e)}"
            logger.error(error_message)
            
            # 创建错误结果块
            error_chunk = DialogueChunk(
                user_id=self.user_id,
                thread_id=self.thread_id,
                dialogue_id=self.dialogue_id,
                chunk_type=ChunkType.TOOL_RESULT,
                role="tool",
                tool_id=tool_id,
                tool_name=tool_class.name,
                output_text=error_message,
                sequence=sequence,
                is_final=True
            )
            
            if self.save_chunk_callback:
                self.save_chunk_callback(error_chunk)
            
            # 使用model_dump获取标准化的格式
            error_data = error_chunk.model_dump()
            
            yield error_data
