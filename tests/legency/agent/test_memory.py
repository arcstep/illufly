import pytest
import asyncio
import zmq.asyncio
import logging
import tempfile
import shutil
import json

from illufly.rocksdb import IndexedRocksDB
from illufly.mq.service import ServiceRouter, ClientDealer
from illufly.community.models import TextChunk, TextFinal, ToolCallFinal, BlockType
from illufly.community.openai import ChatOpenAI
from illufly.community.base_tool import BaseTool
from illufly.agent.chat import ChatAgent, MemoryTopic, MemoryChunk
from illufly.thread import QuestionBlock, AnswerBlock

logger = logging.getLogger(__name__)

@pytest.fixture
def db_path():
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path)

@pytest.fixture
def db(db_path):
    db = IndexedRocksDB(db_path)
    try:
        yield db
    finally:
        db.close()

@pytest.fixture
def agent(db):
    router_address = "inproc://router_abc"
    llm = ChatOpenAI(imitator="QWEN", model="qwen-plus")
    agent = ChatAgent(llm=llm, db=db, router_address=router_address)
    return agent

@pytest.mark.asyncio
async def test_archive_messages(agent, db):
    """测试基本聊天功能"""
    user_id = "test_user"
    thread_id = "test_basic_thread"

    # 确认没有记忆
    topics = db.values(prefix=MemoryTopic.get_user_prefix(user_id, thread_id))
    assert len(topics) == 0

    chunks = db.values(prefix=MemoryChunk.get_user_prefix(user_id, thread_id))
    assert len(chunks) == 0

    # 测试归档
    await agent._archive_messages(
        user_id=user_id,
        thread_id=thread_id,
        question=QuestionBlock(text="你好"),
        answer=AnswerBlock(text="你好")
    )

    # 确认有记忆
    topics = db.values(prefix=MemoryTopic.get_user_prefix(user_id, thread_id))
    assert len(topics) == 1
    chunks = db.values(prefix=MemoryChunk.get_user_prefix(user_id, thread_id))
    assert len(chunks) == 1


