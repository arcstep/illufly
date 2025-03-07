import pytest
import json

import logging
from illufly.community.openai import OpenAIEmbeddings

logger = logging.getLogger(__name__)

@pytest.mark.asyncio
async def test_embeddings_openai():
    """测试 OpenAI 的 embeddings 功能"""
    service = OpenAIEmbeddings(
        model="text-embedding-ada-002"
    )
    embeddings = await service.embed_texts(["Hello, world!"])
    assert len(embeddings) == 1
    assert len(embeddings[0].vector) == 1536

@pytest.mark.asyncio
async def test_embeddings_qwen():
    """测试 Qwen 的 embeddings 功能"""
    service = OpenAIEmbeddings(
        imitator="QWEN",
        model="text-embedding-v3"
    )
    embeddings = await service.embed_texts(["Hello, world!"])
    assert len(embeddings) == 1
    assert len(embeddings[0].vector) == 1024

@pytest.mark.asyncio
async def test_embeddings_zhipu():
    """测试智谱的 embeddings 功能"""
    service = OpenAIEmbeddings(
        imitator="ZHIPU",
        dim=1024,
        model="embedding-3"
    )
    embeddings = await service.embed_texts(["Hello, world!"])
    assert len(embeddings) == 1
    assert len(embeddings[0].vector) == 1024
