import pandas as pd
import re
import html

from typing import List, Dict, Any

from ..prompt import PromptTemplate
from ..rocksdb import default_rocksdb, IndexedRocksDB
from .base import LiteLLM
from .retriever import ChromaRetriever
from .models import MemoryQA

QA_PREFIX = "qa"
MEMORY_COLLECTION = "memory"
DEFAULT_FEEDBACK_PROMPT = "feedback"

class Memory():
    """记忆"""
    def __init__(self, llm: LiteLLM, memory_db: IndexedRocksDB, retriver: ChromaRetriever=None):
        self.memory_db = memory_db
        self.retriver = retriver or ChromaRetriever()
        self.retriver.get_or_create_collection(MEMORY_COLLECTION)
        self.llm = llm

    async def init_retriever(self):
        """初始化记忆"""
        for qa in self.memory_db.values(prefix=QA_PREFIX):
            await self.retriver.add(
                qa.texts,
                user_id=qa.user_id,
                collection_name=MEMORY_COLLECTION,
                metadatas=qa.metadatas
            )
    
    async def extract(self, input_messages: List[Dict[str, Any]], existing_memory: str=None, user_id: str=None, **kwargs) -> str:
        """提取记忆"""
        if user_id is None:
            user_id = "default"

        if existing_memory is None:
            existing_memory = await self.retrieve(input_messages, user_id)

        # 提取新的用户反馈
        feedback_prompt = PromptTemplate(DEFAULT_FEEDBACK_PROMPT)
        feedback_input = feedback_prompt.format({
            "memory": existing_memory,
            "messages": input_messages
        })
        resp = await self.llm.acompletion(feedback_input, stream=False, **kwargs)
        feedback_text = resp.choices[0].message.content
        tables = self.safe_extract_markdown_tables(feedback_text)
        for table in tables:
            qa_dict = table.to_dict('records')
            if "主题" in qa_dict and "问题" in qa_dict and "答案" in qa_dict:
                qa = MemoryQA(
                    user_id=user_id,
                    topic=qa_dict["主题"],
                    question=qa_dict["问题"],
                    answer=qa_dict["答案"]
                )
                # 持久化存储
                self.memory_db.update_with_indexes(MemoryQA.__name__, qa.get_key(user_id, qa.topic, qa.question_hash), qa)
                # 更新到向量数据库
                self.retriver.add(qa.texts, user_id=qa.user_id, collection_name="memory", metadatas=qa.metadatas)

    async def retrieve(self, input_messages: List[Dict[str, Any]], user_id: str=None) -> str:
        """检索记忆"""
        if user_id is None:
            user_id = "default"

        results = await self.retriver.query(
            texts=[self.from_messages_to_text(input_messages)],
            user_id=user_id,
            collection_name=MEMORY_COLLECTION,
            threshold=0.3,
            query_config={"n_results": 10}
        )
        
        items = [f'|{r["topic"]}|{r["question"]}|{r["answer"]}|' for r in results[0]["metadatas"]]
        return "\n".join(list(dict.fromkeys(items)))
    
    def inject(self, input_messages: List[Dict[str, Any]], existing_memory: str=None) -> List[Dict[str, Any]]:
        """注入记忆"""
        if existing_memory and input_messages[0].get("role", None) == "system":
            input_messages[0]["content"] += f"\n\n**用户记忆清单**\n|主题|问题|答案|\n|---|---|---|\n{existing_memory}\n"
        return input_messages

    def from_messages_to_text(self, input_messages: List[Dict[str, Any]]) -> str:
        """将消息转换为文本"""
        return "\n".join([f"{m['role']}: {str(m['content'])}" for m in input_messages])

    def safe_extract_markdown_tables(self, md_text: str) -> List[pd.DataFrame]:
        """安全提取Markdown表格为结构化数据（支持多表）"""
        tables = []
        # 匹配所有表格（非贪婪模式）
        table_blocks = re.finditer(
            r'\|(.+?)\|\n\|([\-: ]+\|)+\n((?:\|.*\|\n?)+)',
            md_text,
            re.DOTALL
        )
        
        for table in table_blocks:
            try:
                headers = [h.strip() for h in table.group(1).split('|') if h.strip()]
                rows = []
                
                for row in table.group(3).split('\n'):
                    if not row.strip():
                        continue
                    cells = [
                        html.unescape(cell).strip() 
                        for cell in row.split('|')[1:-1]
                    ]
                    if len(cells) == len(headers):
                        rows.append(cells)
                
                if headers and rows:
                    tables.append(pd.DataFrame(rows, columns=headers))
            except Exception as e:
                print(f"表格解析失败: {e}")
        
        return tables
