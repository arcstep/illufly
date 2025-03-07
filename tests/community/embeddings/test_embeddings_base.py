import pytest
import asyncio
from unittest import mock
import numpy as np
from typing import List

from illufly.community.base_embeddings import BaseEmbeddings, EmbeddingText
from illufly.rocksdb import IndexedRocksDB


# 创建一个测试用的嵌入模型实现
class MockEmbeddings(BaseEmbeddings):
    """用于测试的嵌入模型实现"""
    
    def __init__(self, **kwargs):
        super().__init__(model="mock_model", dim=8, **kwargs)
        self.embed_count = 0  # 记录调用次数
        
    async def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        """简单的Mock实现，为每个文本生成不同的向量"""
        self.embed_count += 1
        return [
            [float(hash(text + str(i)) % 100) / 100 for i in range(self.dim)]
            for text in texts
        ]

# 模拟RocksDB
class MockRocksDB:
    def __init__(self):
        self.db = {}
        self.models = {}
    
    def register_model(self, model_name, model_class):
        self.models[model_name] = model_class
    
    def key_exist(self, key):
        return key in self.db, None
    
    def update_with_indexes(self, model_name, key, value):
        self.db[key] = value
        
    def get_by_key(self, model_name, key):
        return self.db.get(key)

# 测试
class TestBaseEmbeddings:
    
    @pytest.fixture
    def mock_db(self):
        return MockRocksDB()
    
    @pytest.fixture
    def embeddings(self, mock_db):
        return MockEmbeddings(db=mock_db)
    
    @pytest.mark.asyncio
    async def test_single_text_embedding(self, embeddings):
        """测试单个文本的嵌入"""
        text = "这是测试文本"
        result = await embeddings.embed_texts(text)
        
        assert len(result) == 1
        assert isinstance(result[0], EmbeddingText)
        assert result[0].text == text
        assert result[0].model == "mock_model"
        assert result[0].dim == 8
        assert len(result[0].vector) == 8
        
    @pytest.mark.asyncio
    async def test_multiple_texts_embedding(self, embeddings):
        """测试多个文本的嵌入"""
        texts = ["第一个文本", "第二个文本", "第三个文本"]
        results = await embeddings.embed_texts(texts)
        
        assert len(results) == 3
        for i, result in enumerate(results):
            assert result.text == texts[i]
            assert len(result.vector) == 8
            
    @pytest.mark.asyncio
    async def test_batch_processing(self, embeddings):
        """测试批处理功能 - 确保大数据集被正确分批"""
        # 设置较小的批次大小
        embeddings.max_lines = 2
        
        # 创建超过一个批次的文本
        texts = [f"文本 {i}" for i in range(5)]
        
        # 记录初始调用次数
        initial_count = embeddings.embed_count
        
        results = await embeddings.embed_texts(texts)
        
        # 应该有3次调用 (5篇文章分成2+2+1)
        assert embeddings.embed_count - initial_count == 3
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_caching_behavior(self, embeddings, mock_db):
        """测试缓存行为 - 确保已嵌入的文本不会重复嵌入"""
        text = "缓存测试文本"
        
        # 第一次调用应该嵌入文本
        initial_count = embeddings.embed_count
        result1 = await embeddings.embed_texts(text)
        assert embeddings.embed_count - initial_count == 1
        
        # 第二次调用应该使用缓存
        result2 = await embeddings.embed_texts(text)
        assert embeddings.embed_count - initial_count == 1  # 调用次数不变
        
        # 即使在批量调用中也应使用缓存
        texts = ["新文本1", text, "新文本2"]
        initial_count = embeddings.embed_count
        results = await embeddings.embed_texts(texts)
        
        # 只有新文本被嵌入
        assert embeddings.embed_count - initial_count == 1
        assert len(results) == 2  # 只返回新嵌入的文本
        
    @pytest.mark.asyncio
    async def test_large_batch_consistency(self, embeddings):
        """测试大批量处理的一致性"""
        # 创建100个文本
        large_texts = [f"大批量文本 {i}" for i in range(100)]
        embeddings.max_lines = 10  # 设置批大小为10
        
        results = await embeddings.embed_texts(large_texts)
        
        # 确保所有文本都得到了处理
        assert len(results) == 100
        
        # 验证每个结果
        for i, result in enumerate(results):
            assert result.text == large_texts[i]
            assert len(result.vector) == 8
            
    @pytest.mark.asyncio
    async def test_empty_input(self, embeddings):
        """测试空输入"""
        results = await embeddings.embed_texts([])
        assert results == []
        
    @pytest.mark.asyncio
    async def test_invalid_input(self, embeddings):
        """测试无效输入"""
        with pytest.raises(ValueError):
            await embeddings.embed_texts(123)  # 非字符串或列表
            
