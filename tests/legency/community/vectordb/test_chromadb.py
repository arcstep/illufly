import pytest
import asyncio
import chromadb
import logging

from typing import List
from illufly.community.chroma.chroma_db import ChromaDB
from illufly.community.base_embeddings import BaseEmbeddings

logger = logging.getLogger(__name__)

# 实际的测试用嵌入模型
class MockEmbeddings(BaseEmbeddings):
    """用于测试的简单嵌入模型"""
    
    def __init__(self, **kwargs):
        super().__init__(model="test_model", dim=4, **kwargs)
        
    async def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        """生成简单但独特的文本向量"""
        return [
            [
                hash(text) % 100 / 100, len(text) / 100, 
                sum(ord(c) for c in text) % 100 / 100, 0.5
            ]
            for text in texts
        ]

class TestChromaDBIntegration:
    
    @pytest.fixture
    def embeddings(self):
        """创建测试嵌入模型"""
        return MockEmbeddings()
    
    @pytest.fixture
    def chroma_client(self):
        """创建实际的ChromaDB内存客户端"""
        client = chromadb.Client()
        yield client
        # 测试后清理所有集合
        for collection in client.list_collections():
            client.delete_collection(collection)
    
    @pytest.fixture
    def chroma_db(self, embeddings, chroma_client):
        """创建ChromaDB测试实例"""
        return ChromaDB(embeddings=embeddings, client=chroma_client)
    
    @pytest.mark.asyncio
    async def test_collection_lifecycle(self, chroma_db, chroma_client):
        """测试集合的创建和删除"""
        # 创建集合
        collection_name = "test_lifecycle"
        collection = chroma_db.create_collection(collection_name)
        
        # 验证集合存在
        collections = chroma_client.list_collections()
        assert collection_name in collections
        
        # 删除集合
        chroma_db.delete_collection(collection_name)
        
        # 验证集合已删除
        collections = chroma_client.list_collections()
        assert not collection_name in collections
    
    @pytest.mark.asyncio
    async def test_add_and_query(self, chroma_db):
        """测试添加文本和查询功能"""
        collection_name = "test_add_query"
        
        # 准备测试数据
        texts = [
            "这是一篇关于苹果的文档",
            "这是一篇关于橙子的文档",
            "这是一篇关于香蕉的文档",
            "这是一篇关于计算机的文档"
        ]
        
        # 添加文本到集合
        await chroma_db.add(texts, collection_name=collection_name)
        
        # 执行相似性查询 - 应该返回水果相关文档
        fruit_query = "水果百科知识"
        fruit_results = await chroma_db.query(
            fruit_query, 
            collection_name=collection_name,
            n_results=3
        )
        logger.info(f"fruit_results: {fruit_results}")
        
        # 检查查询结果
        assert len(fruit_results["ids"][0]) == 3
        assert len(fruit_results["documents"][0]) == 3
            
    @pytest.mark.asyncio
    async def test_metadata_and_filtering(self, chroma_db):
        """测试元数据和过滤功能"""
        collection_name = "test_filtering"
        
        # 准备带元数据的测试数据
        texts = [
            "红富士苹果产自中国陕西",
            "安岳柠檬是四川特产",
            "泰国香蕉价格便宜",
            "菲律宾芒果很甜"
        ]
        
        # 准备元数据
        metadatas = [
            {"origin": "中国", "type": "苹果", "price": "高"},
            {"origin": "中国", "type": "柠檬", "price": "中"},
            {"origin": "泰国", "type": "香蕉", "price": "低"},
            {"origin": "菲律宾", "type": "芒果", "price": "中"}
        ]
        
        # 添加文本及元数据
        await chroma_db.add(
            texts, 
            collection_name=collection_name,
            metadatas=metadatas
        )
        
        # 过滤查询: 产自中国的水果
        china_results = await chroma_db.query(
            "水果",
            collection_name=collection_name,
            where={"origin": "中国"},
            n_results=4
        )
        logger.info(f"china_results: {china_results}")
        
        # 验证过滤结果
        assert len(china_results["documents"][0]) == 2
        china_docs = china_results["documents"][0]
        assert any("苹果" in doc for doc in china_docs)
        assert any("柠檬" in doc for doc in china_docs)
        
        # 过滤查询: 价格为"中"的水果
        medium_price_results = await chroma_db.query(
            "水果",
            collection_name=collection_name,
            where={"price": "中"},
            n_results=4
        )
        
        # 验证价格过滤结果
        assert len(medium_price_results["documents"][0]) == 2
        docs = medium_price_results["documents"][0]
        assert any("柠檬" in doc for doc in docs)
        assert any("芒果" in doc for doc in docs)
        
        # 文本内容过滤
        text_filter_results = await chroma_db.query(
            "水果",
            collection_name=collection_name,
            where_document={"$contains": "泰国"},
            n_results=4
        )
        
        # 验证文本过滤结果
        assert len(text_filter_results["documents"][0]) == 1
        assert "泰国" in text_filter_results["documents"][0][0]
        assert "香蕉" in text_filter_results["documents"][0][0]