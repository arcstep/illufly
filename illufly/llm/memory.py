import pandas as pd
import re
import html
from datetime import datetime

from typing import List, Dict, Any

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
        for qa in self.memory_db.values(prefix=ROCKSDB_PREFIX):
            qa_data = qa.to_retrieve()
            await self.retriver.add(
                texts=qa_data["texts"],
                user_id=qa.user_id,
                collection_name=CHROMA_COLLECTION,
                metadatas=qa_data["metadatas"]
            )
    
    def all_memory(self, user_id: str=None, limit: int=100) -> List[MemoryQA]:
        """获取所有记忆"""
        if user_id is None:
            return self.memory_db.values(prefix=ROCKSDB_PREFIX, limit=limit)
        else:
            return self.memory_db.values(prefix=MemoryQA.get_prefix(user_id), limit=limit)
    
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
                    key = qa.get_key(user_id, qa.topic, qa.question_hash)
                    logger.info(f"保存记忆到数据库: {key}")
                    self.memory_db.update_with_indexes(
                        MemoryQA.__name__, 
                        key, 
                        qa
                    )
                    
                    # 更新到向量数据库
                    logger.info(f"更新记忆到向量数据库")
                    qa_data = qa.to_retrieve()
                    await self.retriver.add(
                        texts=qa_data["texts"],
                        user_id=qa.user_id, 
                        collection_name="memory", 
                        metadatas=qa_data["metadatas"]
                    )
                    
                    # 添加到返回结果
                    extracted_memories.append(qa)
                    logger.info(f"成功提取记忆: 主题={qa.topic}, 问题={qa.question}")
                except Exception as e:
                    logger.error(f"处理记忆行时出错: {e}")
                    continue
        
        logger.info(f"记忆提取完成，共提取 {len(extracted_memories)} 条记忆")
        return extracted_memories

    async def retrieve(self, input_messages: List[Dict[str, Any]], user_id: str=None, threshold: float=0.5, top_k: int=10) -> List[MemoryQA]:
        """检索记忆"""
        if user_id is None:
            user_id = "default"

        results = await self.retriver.query(
            texts=[from_messages_to_text(input_messages)],
            user_id=user_id,
            collection_name=CHROMA_COLLECTION,
            threshold=threshold,
            query_config={"n_results": top_k}
        )
        
        # 创建MemoryQA对象并去重
        memory_objects = []
        seen_keys = set()
        for meta in results[0]["metadatas"]:
            key = f"{meta['topic']}:{meta['question']}"
            if key not in seen_keys:
                memory = MemoryQA(
                    user_id=user_id,
                    topic=meta["topic"],
                    question=meta["question"],
                    answer=meta["answer"],
                    created_at=meta.get("created_at", datetime.now().timestamp())
                )
                memory_objects.append(memory)
                seen_keys.add(key)
        
        logger.info(f"\nmemory.retrieve >>> {len(memory_objects)} 个记忆片段")
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
