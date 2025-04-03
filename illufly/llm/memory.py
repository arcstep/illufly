import pandas as pd
import re
import html
from datetime import datetime
from typing import List, Dict, Any, Union
import uuid

from ..prompt import PromptTemplate
from ..rocksdb import default_rocksdb, IndexedRocksDB
from .base import LiteLLM
from .retriever import ChromaRetriever
from .models import MemoryQA

import logging
logger = logging.getLogger(__name__)

ROCKSDB_PREFIX = "mem"
CHROMA_COLLECTION = "memory"
DEFAULT_FEEDBACK_PROMPT = "feedback"

def from_messages_to_text(input_messages: List[Dict[str, Any]]) -> str:
    """将消息转换为文本
    
    处理不同类型的消息，安全提取内容
    """
    result = []
    for m in input_messages:
        role = m.get('role', 'unknown')
        
        # 安全获取内容，处理不同类型的消息
        if 'content' in m:
            content = str(m['content'])
        elif 'chunk_type' in m and m.get('chunk_type') == 'memory_retrieve':
            # 记忆检索消息可能包含memory对象而非content
            mem = m.get('memory', {})
            content = f"记忆: {mem.get('topic', '')}/{mem.get('question', '')}"
        elif 'chunk_type' in m and m.get('chunk_type') == 'memory_extract':
            # 记忆提取消息可能包含memory对象而非content
            mem = m.get('memory', {})
            content = f"提取: {mem.get('topic', '')}/{mem.get('question', '')}"
        elif 'tool_calls' in m:
            # 工具调用消息
            tool_calls = m.get('tool_calls', [])
            content = f"工具调用: {', '.join([tc.get('name', 'unknown') for tc in tool_calls])}"
        else:
            # 处理其他类型的消息或缺少内容的消息
            content = m.get('output_text', '<无内容>')
        
        result.append(f"{role}: {content}")
        
    return "\n".join(result)

class Memory():
    """记忆"""
    def __init__(self, llm: LiteLLM, memory_db: IndexedRocksDB, retriver: ChromaRetriever=None):
        self.memory_db = memory_db
        self.retriver = retriver or ChromaRetriever()
        self.retriver.get_or_create_collection(CHROMA_COLLECTION)
        self.llm = llm

    async def init_retriever(self):
        """初始化记忆"""
        logger.info("开始初始化记忆检索器...")
        
        # 将所有记忆加载到向量库
        for qa in self.memory_db.values(prefix=ROCKSDB_PREFIX):
            try:
                qa_data = qa.to_retrieve()
                # 为问题和答案分别生成唯一的ID
                question_id = f"{qa.memory_id}_q"
                answer_id = f"{qa.memory_id}_a"
                await self.retriver.add(
                    texts=qa_data["texts"],
                    user_id=qa.user_id,
                    collection_name=CHROMA_COLLECTION,
                    metadatas=qa_data["metadatas"],
                    ids=[question_id, answer_id]  # 使用唯一的ID
                )
                logger.info(f"成功加载记忆到向量库: {qa.memory_id}")
            except Exception as e:
                logger.error(f"初始化记忆时出错: {e}, 记忆: {qa}")
                continue
        
        logger.info("记忆检索器初始化完成")

    def all_memory(self, user_id: str=None, limit: int=100) -> List[MemoryQA]:
        """获取所有记忆"""
        if user_id is None:
            return self.memory_db.values(prefix=ROCKSDB_PREFIX, limit=limit)
        else:
            return self.memory_db.values(prefix=MemoryQA.get_prefix(user_id), limit=limit)
    
    async def update_memory(self, user_id: str, memory_id: str, topic: str, question: str, answer: str) -> MemoryQA:
        """更新记忆
        
        Args:
            user_id: 用户ID
            memory_id: 记忆ID，用于唯一标识记忆
            topic: 更新后的主题
            question: 更新后的问题
            answer: 更新后的答案
            
        Returns:
            MemoryQA: 更新后的记忆对象
        """
        if user_id is None:
            raise ValueError("用户ID不能为空")
        
        if topic is None or topic.strip() == "":
            raise ValueError("主题不能为空")
            
        # 首先尝试获取原始记忆
        memory_key = MemoryQA.get_key(user_id, memory_id)
        original_memory = self.memory_db.get(memory_key)
                
        if not original_memory:
            logger.error(f"未找到要更新的记忆: user_id={user_id}, memory_id={memory_id}")
            raise ValueError(f"未找到记忆: {memory_id}")
            
        # 准备更新的记忆对象（保留原始memory_id和created_at）
        updated_memory = MemoryQA(
            user_id=user_id,
            memory_id=memory_id,  # 保留原始memory_id
            topic=topic,
            question=question,
            answer=answer,
            created_at=original_memory.created_at  # 保留原始创建时间
        )
        
        # 事务性更新：保证RocksDB和向量数据库的一致性
        try:
            # 1. 从向量数据库删除旧记录
            await self.retriver.delete(
                ids=[memory_id, memory_id],
                collection_name=CHROMA_COLLECTION
            )
            logger.info(f"成功从向量数据库删除旧记忆: {memory_id}")
            
            # 2. 添加新记录到向量数据库
            qa_data = updated_memory.to_retrieve()
            await self.retriver.add(
                texts=qa_data["texts"],
                user_id=updated_memory.user_id,
                collection_name=CHROMA_COLLECTION,
                metadatas=qa_data["metadatas"],
                ids=qa_data["ids"]
            )
            logger.info(f"成功添加新记忆到向量数据库")
            
            # 3. 更新RocksDB
            self.memory_db.update_with_indexes(
                MemoryQA.__name__,
                memory_key,
                updated_memory
            )
            logger.info(f"成功更新RocksDB中的记忆: {memory_key}")
            
            return updated_memory
            
        except Exception as e:
            logger.error(f"更新记忆时出错: {e}")
            logger.error(f"无法同步更新记忆: {memory_key}")
            # 在生产环境中，可能需要实现回滚机制或发送告警
            raise RuntimeError(f"更新记忆失败: {str(e)}")
    
    async def delete_memory(self, user_id: str, memory_id: str) -> bool:
        """删除记忆
        
        Args:
            user_id: 用户ID
            memory_id: 记忆ID，用于唯一标识记忆
            
        Returns:
            bool: 是否成功删除
        """
        if user_id is None:
            raise ValueError("用户ID不能为空")
        
        if memory_id is None or memory_id.strip() == "":
            raise ValueError("记忆ID不能为空")
            
        # 构建记忆key
        memory_key = MemoryQA.get_key(user_id, memory_id)
            
        # 获取记忆对象
        memory_to_delete = self.memory_db.get(memory_key)
        if not memory_to_delete:
            logger.warning(f"未找到要删除的记忆: key={memory_key}")
            return False
            
        # 事务性删除：先尝试从向量数据库删除
        try:
            await self.retriver.delete(
                ids=[memory_id, memory_id],
                collection_name=CHROMA_COLLECTION
            )
            logger.info(f"成功从向量数据库删除记忆: {memory_id}")
            
            # 删除成功后，从RocksDB删除
            self.memory_db.delete(memory_key)
            logger.info(f"成功从RocksDB删除记忆: {memory_key}")
            
            return True
        except Exception as e:
            logger.error(f"删除记忆时出错: {e}")
            logger.error(f"无法同步删除记忆: {memory_key}")
            # 在生产环境中，可能需要实现回滚机制或发送告警
            return False
    
    async def extract(self, input_messages: List[Dict[str, Any]], model: str, existing_memory: str=None, user_id: str=None, **kwargs) -> List[MemoryQA]:
        """提取记忆"""
        if user_id is None:
            user_id = "default"

        logger.info(f"开始提取记忆，用户ID: {user_id}")
        
        if existing_memory is None:
            logger.info("获取现有记忆...")
            existing_memory = await self.retrieve(input_messages, user_id)

        # 提取新的用户反馈
        feedback_prompt = PromptTemplate(DEFAULT_FEEDBACK_PROMPT)
        feedback_input = feedback_prompt.format({
            "memory": existing_memory,
            "messages": input_messages
        })
        
        logger.info(f"生成记忆提取提示，提示长度: {len(str(feedback_input))}")

        try:
            # 确保使用await调用acompletion
            logger.info(f"调用LLM提取记忆，模型: {model}")
            resp = await self.llm.acompletion(
                messages=feedback_input, 
                model=model, 
                stream=False, 
                **kwargs
            )
            
            # 安全地提取返回内容
            feedback_text = ""
            if (hasattr(resp, 'choices') and 
                resp.choices and 
                hasattr(resp.choices[0], 'message') and 
                hasattr(resp.choices[0].message, 'content')):
                feedback_text = resp.choices[0].message.content
                logger.info(f"收到记忆提取响应，长度: {len(feedback_text)}")
            else:
                logger.warning("\nmemory.extract >>> 无法从响应中提取文本")
                return []
                
        except Exception as e:
            logger.error(f"\nfeedback_input >>> {feedback_input}\n\nmemory.extract >>> [{model}] 提取记忆失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
        
        # 如果返回SKIP，直接返回
        if feedback_text.strip() == "SKIP":
            logger.info("\nmemory.extract >>> SKIP extract")
            return []

        # 提取表格
        tables = self.safe_extract_markdown_tables(feedback_text)
        if not tables:
            logger.info("\nmemory.extract >>> No tables extract")
            return []
        
        # 只处理第一个表格的数据
        table = tables[0]
        if len(table) == 0:
            logger.info("\nmemory.extract >>> Zero lines in tables")
            return []
        
        # 收集所有提取的记忆
        extracted_memories = []
        
        for i, row in table.iterrows():
            if all(k in row.index for k in ["主题", "问题", "答案"]):
                try:
                    qa = MemoryQA(
                        user_id=user_id,
                        topic=row["主题"],
                        question=row["问题"],
                        answer=row["答案"]
                    )
                    
                    # 持久化存储
                    key = MemoryQA.get_key(user_id, qa.memory_id)
                    logger.info(f"保存记忆到数据库: {key}")
                    self.memory_db.update_with_indexes(
                        MemoryQA.__name__, 
                        key, 
                        qa
                    )
                    
                    # 更新到向量数据库
                    logger.info(f"更新记忆到向量数据库")
                    qa_data = qa.to_retrieve()
                    # 为问题和答案分别生成唯一的ID
                    question_id = f"{qa.memory_id}_q"
                    answer_id = f"{qa.memory_id}_a"
                    await self.retriver.add(
                        texts=qa_data["texts"],
                        user_id=qa.user_id, 
                        collection_name="memory", 
                        metadatas=qa_data["metadatas"],
                        ids=[question_id, answer_id]  # 使用唯一的ID
                    )
                    
                    # 添加到返回结果
                    extracted_memories.append(qa)
                    logger.info(f"成功提取记忆: 主题={qa.topic}, 问题={qa.question}")
                except Exception as e:
                    logger.error(f"处理记忆行时出错: {e}")
                    continue
        
        logger.info(f"记忆提取完成，共提取 {len(extracted_memories)} 条记忆")
        return extracted_memories

    async def retrieve(self, input_messages: Union[List[Dict[str, Any]], str], user_id: str=None, threshold: float=1.5, top_k: int=15) -> List[MemoryQA]:
        """检索记忆或搜索记忆
        
        可以接受消息列表或单个查询文本作为输入
        
        Args:
            input_messages: 可以是消息列表或单个查询文本
            user_id: 用户ID
            threshold: 距离阈值，Chroma余弦距离范围为0-2，越小越相似，默认1.5
            top_k: 返回结果数量，默认15个
            
        Returns:
            List[MemoryQA]: 检索或搜索结果列表，每个结果附带distance属性
        """
        if user_id is None:
            user_id = "default"
            
        # 如果是单个字符串，直接作为查询使用
        if isinstance(input_messages, str):
            query_text = input_messages
            if not query_text.strip():
                return []
        else:
            # 否则按照消息列表处理
            query_text = from_messages_to_text(input_messages)

        logger.info(f"\nmemory.retrieve >>> 开始检索记忆")
        logger.info(f"查询文本: {query_text}")
        logger.info(f"用户ID: {user_id}")
        logger.info(f"阈值: {threshold}")
        logger.info(f"top_k: {top_k}")

        results = await self.retriver.query(
            texts=[query_text],
            user_id=user_id,
            collection_name=CHROMA_COLLECTION,
            threshold=threshold,
            query_config={"n_results": top_k}
        )
        
        logger.info(f"\nmemory.retrieve >>> 向量检索结果:")
        logger.info(f"结果数量: {len(results)}")
        if results and results[0]:
            logger.info(f"第一个结果包含:")
            logger.info(f"- 元数据数量: {len(results[0].get('metadatas', []))}")
            logger.info(f"- 距离数量: {len(results[0].get('distances', []))}")
            logger.info(f"- 文档数量: {len(results[0].get('documents', []))}")
            logger.info(f"- ID数量: {len(results[0].get('ids', []))}")
            
            if results[0].get('distances'):
                logger.info(f"距离值: {results[0]['distances']}")
            if results[0].get('metadatas'):
                logger.info(f"元数据: {results[0]['metadatas']}")
        
        # 如果没有结果，返回空列表
        if not results or not results[0] or not results[0]["metadatas"]:
            logger.info("\nmemory.retrieve >>> 未找到相关记忆")
            return []
            
        metadatas = results[0]["metadatas"]
        distances = results[0].get("distances", [])
        
        # 创建MemoryQA对象并去重
        memory_objects = []
        seen_keys = set()
        
        for i, meta in enumerate(metadatas):
            key = f"{meta['topic']}:{meta['question']}"
            if key not in seen_keys:
                memory = MemoryQA(
                    user_id=user_id,
                    topic=meta["topic"],
                    question=meta["question"],
                    answer=meta["answer"],
                    created_at=meta.get("created_at", datetime.now().timestamp()),
                    distance=distances[i] if distances and i < len(distances) else None,
                    memory_id=meta.get("memory_id", results[0]["ids"][i] if results[0].get("ids") and i < len(results[0]["ids"]) else uuid.uuid4().hex)
                )
                
                memory_objects.append(memory)
                seen_keys.add(key)
                logger.info(f"\nmemory.retrieve >>> 创建记忆对象:")
                logger.info(f"- 主题: {memory.topic}")
                logger.info(f"- 问题: {memory.question}")
                logger.info(f"- 距离: {memory.distance}")
                logger.info(f"- 记忆ID: {memory.memory_id}")
        
        # 按距离排序，最相似的排前面
        if distances:
            memory_objects.sort(key=lambda x: getattr(x, "distance", float('inf')))
            logger.info("\nmemory.retrieve >>> 排序后的距离值:")
            for m in memory_objects:
                logger.info(f"- {m.topic}: {m.distance}")
        
        logger.info(f"\nmemory.retrieve >>> 最终返回 {len(memory_objects)} 个记忆片段")
        return memory_objects
    
    def inject(self, messages: List[Dict[str, Any]], memory_table: str) -> List[Dict[str, Any]]:
        """注入记忆

        在system消息中注入记忆，如果没有system消息则添加
        """
        if not memory_table or not memory_table.strip():
            return messages
        
        # 注入记忆
        if any(m.get("role", None) == "system" for m in messages):
            # 添加到已有system消息
            for i, m in enumerate(messages):
                if m.get("role", None) == "system":
                    messages[i]["content"] = f"{m['content']}\n你有以下历史知识记忆：{memory_table}"
                    break
        else:
            # 添加新system消息
            messages = [{"role": "system", "content": f"你有以下历史知识记忆：{memory_table}"}, *messages]
        
        return messages

    def from_messages_to_text(self, input_messages: List[Dict[str, Any]]) -> str:
        """将消息转换为文本"""
        return from_messages_to_text(input_messages)

    def safe_extract_markdown_tables(self, md_text: str) -> List[pd.DataFrame]:
        """安全提取Markdown表格为结构化数据（支持多表）"""
        tables = []
        # 将输入文本按照空行分割，以便处理多个表格
        blocks = re.split(r'\n\s*\n', md_text)
        
        # 匹配单个表格的模式
        table_pattern = re.compile(
            r'^\s*\|(.+?)\|\s*\n\s*\|([\-: ]+\|)+\s*\n((?:\s*\|.+\|\s*\n?)+)',
            re.MULTILINE
        )
        
        for block in blocks:
            if not block.strip():
                continue
            
            match = table_pattern.search(block)
            if not match:
                continue
            
            try:
                # 提取表头
                headers = [h.strip() for h in match.group(1).split('|') if h.strip()]
                
                # 提取数据行
                rows = []
                for row in match.group(3).strip().split('\n'):
                    if not row.strip():
                        continue
                    # 分割并清理单元格数据
                    cells = [
                        html.unescape(cell).strip() 
                        for cell in row.split('|')[1:-1]  # 去掉首尾的空字符串
                    ]
                    if len(cells) == len(headers):
                        rows.append(cells)
                
                if headers and rows:
                    tables.append(pd.DataFrame(rows, columns=headers))
                
            except Exception as e:
                logger.error(f"表格解析失败: {e}")
        
        return tables
