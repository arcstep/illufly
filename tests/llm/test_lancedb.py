import pytest
import pandas as pd
from illufly.llm.retriever.lancedb import LanceRetriever
import illufly.llm.retriever.lancedb as ldb_module

# ----------------- Fake DB & Table -----------------

class FakeTable:
    def __init__(self, name, rows):
        self.name = name
        self._rows = list(rows)
        self.deleted_clauses = []
        self.index_created = False
        self.closed = False
    def add(self, records):
        # 确保复制记录，而不是仅存储引用
        for record in records:
            # 深复制记录，特别是处理向量数据
            record_copy = record.copy()
            if "vector" in record and isinstance(record["vector"], list):
                # 确保向量被正确复制
                record_copy["vector"] = record["vector"].copy()
            self._rows.append(record_copy)
    def delete(self, where_clause):
        self.deleted_clauses.append(where_clause)
        # 如果是建表时删除示例行 (text = ''), 真正把 rows 清空
        if where_clause.strip() == "text = ''":
            self._rows = []
    def search(self, embedding):
        self.last_search_embedding = embedding
        return self
    def where(self, clause):
        self.last_where_clause = clause
        return self
    def limit(self, n):
        self.last_limit = n
        return self
    def to_pandas(self):
        return pd.DataFrame(self._rows)
    async def create_index(self, vector_column_name, metric):
        self.index_created = True
    def close(self):
        self.closed = True

class FakeDB:
    def __init__(self):
        self._tables = {}
    def table_names(self):
        return list(self._tables.keys())
    def open_table(self, name):
        return self._tables[name]
    def create_table(self, name, data):
        tbl = FakeTable(name, data)
        self._tables[name] = tbl
        return tbl

# 自动在所有测试中替换 lancedb.connect
@pytest.fixture(autouse=True)
def fake_db(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(ldb_module.lancedb, "connect", lambda path: fake)
    return fake

# 重写模型返回可变长度 embedding
@pytest.fixture
def retriever(fake_db):
    r = LanceRetriever(output_dir="unused")
    class DummyModel:
        async def aembedding(self, text, **kwargs):
            length = (len(text) % 3) + 1
            embedding = [float(i) for i in range(length)]
            return type("R", (), {"data":[{"embedding":embedding}]})
        async def close(self): pass
    r.model = DummyModel()
    return r

# ----------------- 单元测试 -----------------

@pytest.mark.asyncio
async def test_add_and_get_stats_and_list(retriever, fake_db):
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
    assert "col1" in fake_db.table_names()
    table = fake_db.open_table("col1")
    # 动态长度的 embedding
    rec = table._rows[0]
    assert isinstance(rec["vector"], list)
    assert len(rec["vector"]) == 3  # "hello" 长度 5 => (5%3)+1 = 3

    # 3. get_stats 验证
    stats = await retriever.get_stats("col1")
    assert stats["col1"]["total_vectors"] == 1
    assert stats["col1"]["unique_users"] == 1
    assert stats["col1"]["unique_documents"] == 1

    # 4. list_collections（无前缀默认返回空）
    assert await retriever.list_collections() == []

@pytest.mark.asyncio
async def test_list_collections_with_prefix(fake_db, retriever):
    # 模拟已创建 'vectors_test' 表
    fake_db._tables["vectors_test"] = FakeTable("vectors_test", [])
    collections = await retriever.list_collections()
    assert "test" in collections

@pytest.mark.asyncio
async def test_delete_single_and_multi(retriever, fake_db):
    # 准备表
    fake_db._tables["dT"] = FakeTable("dT", [])
    # 单值删除
    resp1 = await retriever.delete(
        collection_name="dT",
        user_id="u1",
        document_id="d1"
    )
    assert resp1["success"] is True
    tbl = fake_db.open_table("dT")
    assert tbl.deleted_clauses[-1] == "user_id = 'u1' AND document_id = 'd1'"

    # 多值删除
    resp2 = await retriever.delete(
        collection_name="dT",
        user_id=["u1","u2"],
        document_id=["d1","d2"]
    )
    assert resp2["success"] is True
    assert tbl.deleted_clauses[-1] == "user_id IN ('u1', 'u2') AND document_id IN ('d1', 'd2')"

@pytest.mark.asyncio
async def test_query_results_filtering(retriever, fake_db):
    # 准备一条符合 _distance < threshold 的假数据
    fake_db._tables["qT"] = FakeTable("qT", [{
        "text": "t1",
        "user_id": "u1",
        "document_id": "d1",
        "chunk_index": 0,
        "original_name": "n1",
        "source_type": "s1",
        "source_url": "url1",
        "metadata_json": "{\"extra\": 42}",
        "_distance": 0.2
    }])
    # 执行查询
    results = await retriever.query(
        query_texts="xx",
        collection_name="qT",
        user_id="u1",
        document_id="d1",
        limit=5,
        threshold=0.7
    )
    # 结果格式校验
    assert isinstance(results, list) and len(results) == 1
    item = results[0]["results"][0]
    assert item["text"] == "t1"
    assert item["score"] == 0.2
    assert item["metadata"]["user_id"] == "u1"
    assert item["metadata"]["document_id"] == "d1"
    assert item["metadata"]["extra"] == 42

@pytest.mark.asyncio
async def test_ensure_index(retriever, fake_db):
    # 数据量不足，不建索引
    fake_db._tables["eT"] = FakeTable("eT", [{"a":1}] * 10)
    ok1 = await retriever.ensure_index("eT")
    assert ok1 is False
    assert not fake_db.open_table("eT").index_created

    # 数据量足够，建索引
    fake_db._tables["eT2"] = FakeTable("eT2", [{"a":1}] * 150)
    ok2 = await retriever.ensure_index("eT2")
    assert ok2 is True
    assert fake_db.open_table("eT2").index_created

@pytest.mark.asyncio
async def test_close_closes_tables_and_db(retriever, fake_db):
    # 准备多张表
    fake_db._tables["c1"] = FakeTable("c1", [])
    fake_db._tables["c2"] = FakeTable("c2", [])
    # 关闭调用
    ok = await retriever.close()
    assert ok is True
    # retriever.db 应被置 None
    assert retriever.db is None
    # 所有表的 close() 都被调用
    for tbl in fake_db._tables.values():
        assert tbl.closed is True
