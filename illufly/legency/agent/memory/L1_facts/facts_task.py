from typing import List, Optional, ClassVar, Dict, Any

import asyncio
import json
import logging

from ...mq import BlockType
from ...async_utils import AsyncUtils
from ...envir import get_env
from ...rocksdb import IndexedRocksDB
from ...prompt_template import PromptTemplate
from ..L0_qa import QA, HistoryMessage
from ...llm.chat_openai import ChatOpenAI
from ...memory.types import TaskState, MemoryType
from ..base_task import BaseTask
from .models import Fact

class FactsTask(BaseTask):
    """提取事实任务"""
    
    @classmethod
    def get_error_tasks(cls, db: IndexedRocksDB, limit: int = None):
        """获取处理失败的QA列表"""
        limit = limit or 1000
        values = db.values_with_index(
            model_name=MemoryType.QA,
            field_path="task_extract_facts",
            field_value=TaskState.ERROR,
            limit=limit
        )
        return [QA(**v) for v in values] if values else []

    @classmethod
    def get_processing_tasks(cls, db: IndexedRocksDB, limit: int = None):
        """获取处理中的QA列表"""
        limit = limit or 1000
        values = db.values_with_index(
            model_name=MemoryType.QA,
            field_path="task_extract_facts",
            field_value=TaskState.PROCESSING,
            limit=limit
        )
        return [QA(**v) for v in values] if values else []

    @classmethod
    def get_todo_tasks(cls, db: IndexedRocksDB, limit: int = None):
        """获取待处理的QA列表"""
        limit = limit or 1000
        values = db.values_with_index(
            model_name=MemoryType.QA,
            field_path="task_extract_facts",
            field_value=TaskState.TODO,
            limit=limit
        )
        return [QA(**v) for v in values] if values else []

    @classmethod
    def fetch_task(cls, db: IndexedRocksDB):
        """获取待处理的QA列表"""
        values = db.values_with_index(
            model_name=MemoryType.QA,
            field_path="task_extract_facts",
            field_value=TaskState.TODO,
            limit=1
        )
        qa = QA(**values[0]) if values else None
        if qa:
            qa.task_extract_facts = TaskState.PROCESSING
            db.update_with_indexes(MemoryType.QA, qa.key, qa.model_dump())
            updated_qa = QA(**db[qa.key])
            logging.debug(f"获取QA {qa.qa_id} 并设置为处理中: {updated_qa.task_extract_facts}")
        return qa

    @classmethod
    async def _generate_facts(
        cls,
        db: IndexedRocksDB,
        messages: List[Dict[str, Any]],
        question: str,
        answer: str,
        assistant: ChatOpenAI
    ):
        """生成事实"""
        # logger.debug(f"开始处理摘要任务， memory: {messages}, content: {content}")
        chat = assistant

        template = PromptTemplate(template_id="facts")
        resp = chat.async_call(
            messages="请开始生成事实",
            system_template=template,
            bindings={"memory": messages, "question": question, "answer": answer}
        )

        final_text = ""
        async for chunk in resp:
            # logger.debug(f"摘要任务 {messages} 的响应: {chunk}")
            if chunk.block_type == BlockType.TEXT_CHUNK:
                final_text += chunk.text

        if len(final_text) > 10:
            fact = Fact(
                user_id=qa.user_id,
                thread_id=qa.thread_id,
                title=final_text[:30],
                content=final_text,
                source_chat_threads=[qa.qa_id]
            )
            db.update_with_indexes(MemoryType.FACT, fact.key, fact.model_dump())

    @classmethod
    def reset_processing_task(cls, db: IndexedRocksDB, batch_size: int = None):
        """重置任务状态为处理中"""
        batch_size = batch_size or 1024*10
        while True:
            items = db.values_with_index(
                model_name=MemoryType.QA,
                field_path="task_extract_facts",
                field_value=TaskState.PROCESSING,
                limit=batch_size
            )
            if not items:
                break

            for item in items:
                qa = QA(**item)
                qa.task_extract_facts = TaskState.TODO
                db.update_with_indexes(MemoryType.QA, qa.key, qa.model_dump())

    # 以下是 BaseTask 要求的抽象方法实现

    @classmethod
    async def fetch_todo_task(cls, db: IndexedRocksDB, **kwargs):
        """获取一个待处理的任务，如果没有则返回None"""
        values = db.values_with_index(
            model_name=MemoryType.QA,
            field_path="task_extract_facts",
            field_value=TaskState.TODO,
            limit=1
        )
        return QA(**values[0]) if values else None
        
    @classmethod
    async def task_to_processing(cls, db: IndexedRocksDB, task: Any) -> None:
        """将任务状态更新为处理中"""
        if task and isinstance(task, QA):
            task.task_extract_facts = TaskState.PROCESSING
            db.update_with_indexes(MemoryType.QA, task.key, task.model_dump())
            updated_task = QA(**db[task.key])
            logging.debug(f"获取QA {task.qa_id} 并设置为处理中: {updated_task.task_extract_facts}")
        else:
            logging.warning(f"任务不是QA类型: {task}")

    @classmethod
    async def process_todo_task(cls, db, task: Any, assistant: ChatOpenAI, **kwargs):
        """处理一个事实生成任务"""
        if not isinstance(task, QA) or not task.task_extract_facts == TaskState.PROCESSING:
            raise ValueError(f"任务不是待处理状态的QA类型: {task}")
        
        task_id = cls.get_task_id()
        logger = cls._loggers[task_id]
        # logger.debug(f"开始处理QA {task.qa_id}")

        try:
            messages = [m.message_dict for m in task.messages]
            await cls._generate_facts(db, messages, task.question, task.answer, assistant)
            task.task_extract_facts = TaskState.DONE
            db.update_with_indexes(MemoryType.QA, task.key, task.model_dump())

        except Exception as e:
            logger.error(f"处理QA {task.qa_id} 时发生错误: {e}")
            task.task_extract_facts = TaskState.ERROR
            db.update_with_indexes(MemoryType.QA, task.key, task.model_dump())
