import pytest
import pandas as pd
from illufly.llm.retriever.lancedb import LanceRetriever
import os
from illufly.llm.litellm import init_litellm

# 在测试开始前初始化 LiteLLM 缓存目录，后续测试可走本地缓存
cache_dir = os.path.join(os.path.dirname(__file__), "litellm_cache")
init_litellm(cache_dir)

# 使用真实 LanceDB，tmp_path 作为存储目录
@pytest.fixture
def retriever(tmp_path):
    db_dir = tmp_path / "lance_db"
    r = LanceRetriever(output_dir=str(db_dir))
    # stub 嵌入模型，返回可变长向量
    class DummyModel:
        async def aembedding(self, text, **kwargs):
            length = (len(text) % 3) + 1
            return type("R", (), {"data":[{"embedding":[float(i) for i in range(length)]}]})
        async def close(self): pass
    r.model = DummyModel()
    return r

# ----------------- 单元测试 -----------------

@pytest.mark.asyncio
async def test_add_and_get_stats_and_list(retriever):
    # 1. 添加一条记录
    res = await retriever.add(
        texts="hello",
        collection_name="col1",
        user_id="userA",
        metadatas={"document_id":"doc1"}
    )
    assert res["success"] is True
    assert res["original_count"] == 1
    assert res["skipped"] == 0
    assert res["added"] == 1

    # 2. 表创建与数据存储
    assert "col1" in retriever.db.table_names()
    table = retriever.db.open_table("col1")
    df = table.to_pandas()
    rec = df.iloc[0]
    # 检查向量维度，忽略具体类型（可能是numpy.ndarray）
    assert len(rec["vector"]) == 3

    # 3. get_stats 验证
    stats = await retriever.get_stats("col1")
    assert stats["col1"]["total_vectors"] == 1
    assert stats["col1"]["unique_users"] == 1
    assert stats["col1"]["unique_documents"] == 1

    # 4. list_collections（无前缀默认返回空）
    assert await retriever.list_collections() == []

@pytest.mark.asyncio
async def test_list_collections_with_prefix(retriever):
    # 在真实 DB 中创建名为 vectors_test 的表
    retriever._get_or_create_table("vectors_test")
    collections = await retriever.list_collections()
    assert "test" in collections

@pytest.mark.asyncio
async def test_delete_single_and_multi(retriever):
    # 准备表 dT
    retriever._get_or_create_table("dT")
    # 单值删除
    resp1 = await retriever.delete(
        collection_name="dT",
        user_id="u1",
        document_id="d1"
    )
    assert resp1["success"] is True
    assert resp1["deleted"] == 1

    # 多值删除
    resp2 = await retriever.delete(
        collection_name="dT",
        user_id=["u1","u2"],
        document_id=["d1","d2"]
    )
    assert resp2["success"] is True
    assert resp2["deleted"] == 1

@pytest.mark.asyncio
async def test_query_results_filtering(retriever):
    # 通过 add 插入一条记录
    await retriever.add(
        texts="t1",
        collection_name="qT",
        user_id="u1",
        metadatas={"document_id":"d1"}
    )
    # 执行查询
    results = await retriever.query(
        query_texts="t1",
        collection_name="qT",
        user_id="u1",
        document_id="d1",
        limit=5,
        threshold=0.5
    )
    # 结果格式校验
    assert isinstance(results, list) and len(results) == 1
    item = results[0]["results"][0]
    assert item["text"] == "t1"
    # 检查 distance 是否合理范围内的浮点数
    assert isinstance(item["distance"], float)
    assert item["metadata"]["user_id"] == "u1"
    assert item["metadata"]["document_id"] == "d1"

@pytest.mark.asyncio
async def test_ensure_index(retriever):
    # 数据量不足，不建索引
    tbl1 = retriever._get_or_create_table("eT")
    # 为表添加 10 行（仅为了统计行数）
    row = {
        "vector": [0.0, 0.0, 0.0],  # 使用三维向量
        "text":"", "user_id":"", "document_id":"",
        "chunk_index":0, "original_name":"", "source_type":"",
        "source_url":"", "created_at":0, "metadata_json":"{}"
    }
    tbl1.add([row] * 10)
    ok1 = await retriever.ensure_index("eT")
    assert ok1 is False

    # 数据量足够，建索引
    tbl2 = retriever._get_or_create_table("eT2")
    tbl2.add([row] * 150)
    ok2 = await retriever.ensure_index("eT2")
    assert ok2 is True

@pytest.mark.asyncio
async def test_close_closes_tables_and_db(retriever):
    # 准备多张表
    retriever._get_or_create_table("c1")
    retriever._get_or_create_table("c2")
    # 关闭调用
    ok = await retriever.close()
    assert ok is True
    # retriever.db 应被置 None
    assert retriever.db is None
    # LiteLLM 的模型也应当被关闭
    # （DummyModel.close 不抛错即视为关闭成功）
