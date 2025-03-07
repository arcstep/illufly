import pytest
import json

import logging
from illufly.community.openai import OpenAIEmbeddings

logger = logging.getLogger(__name__)

@pytest.fixture
async def openai_embeddings():
    """OpenAI 服务实例"""
    service = OpenAIEmbeddings(
        model="text-embedding-ada-002"
    )
    return service

@pytest.mark.asyncio
async def test_embeddings_openai(openai_embeddings):
    """测试 OpenAI 的 embeddings 功能"""
    embeddings = await openai_embeddings.embed_texts(["Hello, world!"])
    assert len(embeddings) == 1
    assert len(embeddings[0].vector) == 1536
