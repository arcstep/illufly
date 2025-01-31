from typing import List, Optional, ClassVar, Dict, Any

import asyncio
import json
import logging

from ....mq import BlockType
from ....async_utils import AsyncUtils
from ....envir import get_env
from ....io.rocksdict import IndexedRocksDB
from ...system_template import SystemTemplate
from ...memory.L0_qa import QA, Message
from ...chat_openai import ChatOpenAI
from ...memory.types import TaskState, MemoryType
from ..base_task import BaseTask

class QaTask(BaseTask):
    """对话摘要任务"""

    @classmethod
    def get_tasks(cls, db: IndexedRocksDB, batch_size: int):
        """获取待处理的QA列表"""
        values = db.values_with_indexes(
            model_name=MemoryType.QA,
            field_path="task_summarize",
            field_value=TaskState.TODO,
            limit=batch_size
        )
        return [QA(**value) for value in values]

    @classmethod
    async def _process_summary(
        cls,
        db: IndexedRocksDB,
        messages: List[Dict[str, Any]],
        content: str,
        logger: logging.Logger,
        assistant: Optional[ChatOpenAI] = None
    ):
        """处理摘要"""
        logger.info(f"开始处理摘要任务， memory: {messages}, content: {content}")
        chat = assistant or ChatOpenAI(
            model=get_env("ILLUFLY_L0_TASK_MODEL"),
            prefix=get_env("ILLUFLY_L0_TASK_PREFIX"),
            user_id=get_env("ILLUFLY_L0_TASK_USER_ID"),
            thread_id="once",
            db=db,
            logger=logger
        )
        template = SystemTemplate(template_id="summary")
        logger.info(f"摘要任务 {messages} 的模板: {template}")
        logger.info(f"摘要任务 {messages} 的绑定: {bindings}")
        resp = chat.async_call(
            messages="请开始处理",
            template=template,
            bindings={"memory": messages, "content": content}
        )
        final_text = ""
        async for chunk in resp:
            logger.info(f"摘要任务 {messages} 的响应: {chunk}")
            if chunk.block_type == BlockType.TEXT_CHUNK:
                final_text += chunk.text

        return final_text if final_text else content

    @classmethod
    async def _process_batch(cls, db, batch_size: int = 10, assistant: Optional[ChatOpenAI] = None, **kwargs):
        """处理一批摘要任务"""
        task_id = cls.get_task_id()
        logger = cls._loggers[task_id]
        
        # 获取待处理的QA列表
        qa_list = cls.get_tasks(db, batch_size=batch_size)
        if not qa_list:
            logger.info("没有待处理的QA")
            return
        
        logger.debug(f"获取到 {len(qa_list)} 个待处理QA")
        
        # 处理每个QA
        for qa in qa_list:
            logger.info(f"开始处理QA {qa.qa_id}")
            try:
                if len(qa.question) > 50:
                    messages = [m.message_dict for m in qa.messages]
                    summary_question = await cls._process_summary(messages, qa.question, logger, assistant)
                else:
                    summary_question = qa.question

                if len(qa.answer) > 50:
                    messages = [m.message_dict for m in qa.messages]
                    summary_answer = await cls._process_summary(messages, qa.answer, logger, assistant)
                else:
                    summary_answer = qa.answer

                logger.info(f"处理QA {qa.qa_id} 完成: {summary_question}, {summary_answer}")

                qa.summary = [
                    Message(role="user", content=str(summary_question)),
                    Message(role="assistant", content=str(summary_answer))
                ]
                
                qa.task_summarize = TaskState.DONE
                logger.info(f"准备写入 {qa.qa_id}: {qa.model_dump()}")
                db.update_with_indexes(MemoryType.QA, qa.key, qa.model_dump())

            except Exception as e:
                logger.error(f"处理QA {qa.qa_id} 时发生错误: {e}")
                qa.task_summarize = TaskState.ERROR
                db.update_with_indexes(MemoryType.QA, qa.key, qa.model_dump())
