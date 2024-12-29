"""B树索引

本测试模块验证 BTreeIndex 的所有核心功能和特性。
BTreeIndex 是一个高性能的索引实现，支持多种数据类型和丰富的查询操作。

一、核心特性:

1. 数据类型支持
    - 基础类型: int, float, str, bool
    - 日期时间: datetime
    - 复合键: tuple, 支持混合类型
    - 特殊值: None, inf, -inf, ''
    - 嵌套结构: 支持通过路径访问嵌套字段

2. 查询能力
    - 精确查询: == (精确匹配)
    - 比较查询: >, >=, <, <= (单值比较)
    - 范围查询: [], (), [), (] (区间操作)
    - 复合查询: 支持复合键的范围查询

3. 数据管理
    - 自动更新: 同一 owner_id 的新值会替换旧值
    - 重复值处理: 支持多个 owner_id 关联到同一个值
    - 原子性操作: 保证更新操作的一致性
    - 序列化支持: 可持久化存储

4. 性能特性
    - 高效查询: O(log n) 的查询复杂度
    - 批量操作: 优化的批量插入和查询
    - 内存优化: 通过 B 树结构优化内存使用
    - LRU 缓存: 常用查询结果缓存

二、使用示例:

1. 基础操作:
```python
from illufly.io.jiaozi_cache.index import BTreeIndex

# 创建索引
index = BTreeIndex(order=4) # order 参数影响树的分支因子

# 添加数据
index.add(100, "doc1")
index.add(200, "doc2")

# 查询数据
result = index.search(100) # ["doc1"]
```

2. 范围查询:

```python
# 闭区间查询 [100, 200]
results = index.query("[]", 100, 200)

# 开区间查询 (100, 200)
results = index.query("()", 100, 200)

# 半开区间查询 [100, 200)
results = index.query("[)", 100, 200)
```

3. 复合键:

```python
# 创建复合键索引
index.add((1, "high"), "task1")
index.add((2, "low"), "task2")

# 复合键范围查询
results = index.query("[]", (1, "high"), (2, "low"))
```

4. 日期时间索引:

```python
from datetime import datetime

# 添加时间索引
index.add(datetime(2024, 1, 1), "event1")
index.add(datetime(2024, 1, 2), "event2")

# 时间范围查询
start = datetime(2024, 1, 1)
end = datetime(2024, 1, 2)
results = index.query("[]", start, end)
```

5. 嵌套数据:

```python
# 创建嵌套数据
data = {
    "stats": {
        "views": 100,
        "likes": 50
    }
}
index.add(data["stats"]["views"], "post1")
```

性能考虑:
1. 选择合适的 order 值（默认为 4）
2. 批量操作时考虑使用事务
3. 对于频繁查询的场景，利用查询缓存
4. 定期维护索引以优化性能

注意事项:
1. 键必须是可比较的类型
2. 复合键的所有组件都必须可比较
3. 更新操作会自动处理旧值
4. 范围查询结果可能需要去重

"""

import pytest
from datetime import datetime, timedelta
from illufly.io.jiaozi_cache.index.btree_index_backend import BTreeIndex
from dataclasses import dataclass
from typing import Dict, List, Any, Optional

@dataclass
class ComplexData:
    id: str
    nested: Dict[str, Any]
    tags: List[str]
    created_at: datetime
    updated_at: Optional[datetime] = None

@pytest.fixture
def btree():
    """创建一个 BTreeIndex 实例"""
    return BTreeIndex(order=3)

def test_add_and_search(btree):
    """测试添加和搜索功能"""
    # 添加数据
    btree.add(10, "owner1")
    btree.add(20, "owner2")
    btree.add(5, "owner3")

    # 测试搜索
    assert btree.search(10) == ["owner1"]
    assert btree.search(20) == ["owner2"]
    assert btree.search(5) == ["owner3"]

    # 测试不存在的值
    assert btree.search(15) == []

def test_range_search(btree):
    """测试范围搜索功能"""
    # 添加数据
    btree.add(10, "owner1")
    btree.add(20, "owner2")
    btree.add(5, "owner3")
    btree.add(15, "owner4")

    # 测试范围搜索
    assert set(btree.range_search(5, 15)) == {"owner1", "owner3", "owner4"}
    assert set(btree.range_search(10, 20)) == {"owner1", "owner2", "owner4"}

def test_remove(btree):
    """测试删除功能"""
    # 添加数据
    btree.add(10, "owner1")
    btree.add(20, "owner2")
    btree.add(5, "owner3")

    # 删除数据
    btree.remove("owner1")
    assert btree.search(10) == []

    # 确保其他数据仍然存在
    assert btree.search(20) == ["owner2"]
    assert btree.search(5) == ["owner3"]

def test_datetime_key(btree):
    """测试使用 datetime 作为键"""
    # 添加 datetime 数据
    dt1 = datetime(2024, 1, 1)
    dt2 = datetime(2024, 1, 2)
    btree.add(dt1, "owner1")
    btree.add(dt2, "owner2")

    # 测试搜索
    assert btree.search(dt1) == ["owner1"]
    assert btree.search(dt2) == ["owner2"]

def test_serialization(btree):
    """测试 B 树的序列化和反序列化"""
    # 添加数据
    btree.add(10, "owner1")
    btree.add(20, "owner2")

    # 序列化
    serialized = btree._serialize_tree(btree._tree)
    assert isinstance(serialized, dict)

    # 反序列化
    deserialized_tree = btree._deserialize_tree(serialized)
    assert deserialized_tree is not None
    assert deserialized_tree.keys == btree._tree.keys

def test_compare_ops(btree, caplog):
    """测试单值比较操作符"""
    caplog.set_level("ERROR")  # 只显示错误日志
    
    # 添加测试数据
    btree.add(10, "owner1")
    btree.add(20, "owner2")
    btree.add(15, "owner3")

    # 测试等于
    assert btree.query("==", 10) == ["owner1"]
    assert btree.query("==", 20) == ["owner2"]
    assert btree.query("==", 15) == ["owner3"]
    assert btree.query("==", 25) == []

    # 测试不等于
    assert set(btree.query("!=", 10)) == {"owner2", "owner3"}
    assert set(btree.query("!=", 20)) == {"owner1", "owner3"}

    # 测试大于等于
    assert set(btree.query(">=", 15)) == {"owner2", "owner3"}
    assert set(btree.query(">=", 10)) == {"owner1", "owner2", "owner3"}

    # 测试小于等于
    assert set(btree.query("<=", 15)) == {"owner1", "owner3"}
    assert set(btree.query("<=", 20)) == {"owner1", "owner2", "owner3"}

    # 测试大于
    assert set(btree.query(">", 10)) == {"owner2", "owner3"}
    assert set(btree.query(">", 15)) == {"owner2"}

    # 测试小于
    assert set(btree.query("<", 20)) == {"owner1", "owner3"}
    assert set(btree.query("<", 15)) == {"owner1"}

def test_range_ops(btree, caplog):
    """测试区间比较操作符"""
    caplog.set_level("ERROR")
    
    # 添加数据
    btree.add(10, "owner1")
    btree.add(20, "owner2")
    btree.add(15, "owner3")
    btree.add(25, "owner4")

    # 测试闭区间
    assert set(btree.query("[]", 10, 20)) == {"owner1", "owner2", "owner3"}

    # 测试开区间
    assert set(btree.query("()", 10, 20)) == {"owner3"}
    assert set(btree.query("()", 15, 25)) == {"owner2"}

    # 测试左闭右开
    assert set(btree.query("[)", 10, 20)) == {"owner1", "owner3"}
    assert set(btree.query("[)", 15, 25)) == {"owner3", "owner2"}

    # 测试左开右闭
    assert set(btree.query("(]", 10, 20)) == {"owner3", "owner2"}
    assert set(btree.query("(]", 15, 25)) == {"owner2", "owner4"}

def test_datetime_keys(btree):
    """测试 datetime 类型的键"""
    dt1 = datetime(2024, 1, 1)
    dt2 = datetime(2024, 1, 2)
    dt3 = datetime(2024, 1, 3)

    # 添加 datetime 数据
    btree.add(dt1, "owner1")
    btree.add(dt2, "owner2")
    btree.add(dt3, "owner3")

    # 测试等于
    assert btree.query("==", dt1) == ["owner1"]
    assert btree.query("==", dt2) == ["owner2"]

    # 测试范围
    assert set(btree.query("[]", dt1, dt3)) == {"owner1", "owner2", "owner3"}
    assert set(btree.query("[)", dt1, dt3)) == {"owner1", "owner2"}

def test_nested_key_queries(btree):
    """测试嵌套键值的查询"""
    print("\n=== 开始测试嵌套键值查询 ===")
    
    # 准备测试数据
    data1 = ComplexData(
        id="1",
        nested={"stats": {"views": 100, "likes": 50}},
        tags=["python", "test"],
        created_at=datetime(2024, 1, 1)
    )
    
    data2 = ComplexData(
        id="2",
        nested={"stats": {"views": 200, "likes": 75}},
        tags=["python", "advanced"],
        created_at=datetime(2024, 1, 2)
    )
    
    # 添加数据
    btree.add(data1.nested["stats"]["views"], "data1")
    btree.add(data2.nested["stats"]["views"], "data2")
    
    # 测试范围查询
    result = set(btree.query("[]", 100, 200))
    assert result == {"data1", "data2"}, "应该找到所有在视图范围内的数据"

def test_datetime_range_operations(btree):
    """测试日期时间范围操作"""
    print("\n=== 开始测试日期时间范围操作 ===")
    
    base_date = datetime(2024, 1, 1)
    # 创建一系列时间点
    dates = [base_date + timedelta(days=i) for i in range(5)]
    
    # 添加数据
    for i, date in enumerate(dates):
        btree.add(date, f"record{i}")
    
    # 测试不同的区间操作
    # 闭区间
    result = set(btree.query("[]", dates[1], dates[3]))
    assert result == {"record1", "record2", "record3"}
    
    # 开区间
    result = set(btree.query("()", dates[1], dates[3]))
    assert result == {"record2"}
    
    # 左闭右开
    result = set(btree.query("[)", dates[1], dates[3]))
    assert result == {"record1", "record2"}

def test_composite_key_queries(btree):
    """测试复合键查询"""
    print("\n=== 开始测试复合键查询 ===")
    
    # 创建复合键 (优先级, 时间戳)
    data = [
        ((1, datetime(2024, 1, 1)), "task1"),
        ((1, datetime(2024, 1, 2)), "task2"),
        ((2, datetime(2024, 1, 1)), "task3"),
        ((2, datetime(2024, 1, 2)), "task4"),
    ]
    
    for key, owner_id in data:
        btree.add(key, owner_id)
    
    # 测试复合键的范围查询
    start = (1, datetime(2024, 1, 1))
    end = (2, datetime(2024, 1, 1))
    result = set(btree.query("[]", start, end))
    assert result == {"task1", "task3"}

def test_edge_cases(btree):
    """测试边界情况"""
    print("\n=== 开始测试边界情况 ===")
    
    # 添加一些特殊值
    special_values = [
        (float('-inf'), "minus_inf"),
        (float('inf'), "plus_inf"),
        (None, "null_value"),
        ("", "empty_string"),
        (0, "zero"),
    ]
    
    for value, owner_id in special_values:
        btree.add(value, owner_id)
    
    # 测试特殊值的查询
    assert btree.query("==", None) == ["null_value"]
    assert btree.query("==", "") == ["empty_string"]
    
    # 测试范围查询包含无穷值
    result = set(btree.query("[]", float('-inf'), 0))
    assert result == {"minus_inf", "zero"}

def test_large_dataset_performance(btree):
    """测试大数据集性能"""
    print("\n=== 开始测试大数据集性能 ===")
    
    import time
    
    # 生成测试数据
    n = 1000
    data = [(i, f"item{i}") for i in range(n)]
    
    # 测试插入性能
    start_time = time.time()
    for value, owner_id in data:
        btree.add(value, owner_id)
    insert_time = time.time() - start_time
    
    # 测试查询性能
    start_time = time.time()
    result = btree.query("[]", n//4, n//2)
    query_time = time.time() - start_time
    
    print(f"插入 {n} 条数据用时: {insert_time:.2f}秒")
    print(f"查询 {n//4} 条数据用时: {query_time:.2f}秒")
    
    # 验证结果正确性
    expected_count = n//2 - n//4 + 1
    assert len(result) == expected_count

def test_duplicate_values(btree):
    """测试重复值处理"""
    print("\n=== 开始测试重复值处理 ===")
    
    # 添加具有相同值的多个记录
    btree.add(100, "owner1")
    btree.add(100, "owner2")
    btree.add(100, "owner3")
    
    # 测试等值查询
    result = set(btree.query("==", 100))
    assert result == {"owner1", "owner2", "owner3"}
    
    # 测试删除其中一个值后的查询
    btree.remove("owner2")
    result = set(btree.query("==", 100))
    assert result == {"owner1", "owner3"}

def test_update_operations(btree):
    """测试更新操作"""
    print("\n=== 开始测试更新操作 ===")
    
    # 初始插入
    btree.add(50, "record1")
    
    # 更新现有记录
    btree.add(60, "record1")  # 应该移除旧值并添加新值
    
    # 验证更新结果
    assert btree.query("==", 50) == []
    assert btree.query("==", 60) == ["record1"]

def test_composite_key_comparison(btree):
    """详细测试复合键的比较逻辑"""
    print("\n=== 开始测试复合键比较逻辑 ===")
    
    # 创建测试数据
    data = [
        ((1, datetime(2024, 1, 1)), "task1"),
        ((1, datetime(2024, 1, 2)), "task2"),
        ((2, datetime(2024, 1, 1)), "task3"),
        ((2, datetime(2024, 1, 2)), "task4"),
    ]
    
    # 添加数据并打印树结构
    for key, owner_id in data:
        btree.add(key, owner_id)
        print(f"\n添加 {key} -> {owner_id} 后的树结构:")
        print(btree._debug_print_tree())
    
    # 测试各种范围查询
    test_cases = [
        {
            'start': (1, datetime(2024, 1, 1)),
            'end': (2, datetime(2024, 1, 1)),
            'op': "[]",
            'expected': {"task1", "task3"}
        },
        {
            'start': (1, datetime(2024, 1, 1)),
            'end': (1, datetime(2024, 1, 2)),
            'op': "[]",
            'expected': {"task1", "task2"}
        },
        {
            'start': (1, datetime(2024, 1, 2)),
            'end': (2, datetime(2024, 1, 1)),
            'op': "[]",
            'expected': {"task2", "task3"}
        }
    ]
    
    for case in test_cases:
        print(f"\n测试范围查询: {case['op']} {case['start']} to {case['end']}")
        result = set(btree.query(case['op'], case['start'], case['end']))
        print(f"期望结果: {case['expected']}")
        print(f"实际结果: {result}")
        assert result == case['expected']
        
    # 测试单个复合键的比较
    test_pairs = [
        (
            (1, datetime(2024, 1, 1)),
            (1, datetime(2024, 1, 2)),
            -1  # 期望结果
        ),
        (
            (1, datetime(2024, 1, 2)),
            (2, datetime(2024, 1, 1)),
            -1
        ),
        (
            (2, datetime(2024, 1, 1)),
            (2, datetime(2024, 1, 1)),
            0
        )
    ]
    
    print("\n测试复合键比较:")
    for x, y, expected in test_pairs:
        result = btree._safe_compare(x, y)
        print(f"比较 {x} 和 {y}: 期望 {expected}, 实际 {result}")
        assert result == expected

def test_composite_key_queries_detailed(btree):
    """详细测试复合键的边界情况"""
    print("\n=== 开始测试复合键边界情况 ===")
    
    # 测试数据
    test_data = [
        ((1, datetime(2024, 1, 1)), "task1"),
        ((1, datetime(2024, 1, 2)), "task2"),
        ((2, datetime(2024, 1, 1)), "task3"),
        ((2, datetime(2024, 1, 2)), "task4"),
    ]
    
    # 添加数据时打印详细信息
    for key, owner_id in test_data:
        print(f"\n添加键值对: {key} -> {owner_id}")
        btree.add(key, owner_id)
        print("当前树结构:")
        print(btree._debug_print_tree())
        
    # 测试边界情况
    test_cases = [
        {
            'desc': "精确边界",
            'start': (1, datetime(2024, 1, 1)),
            'end': (2, datetime(2024, 1, 1)),
            'op': "[]",
            'expected': {"task1", "task3"}
        },
        {
            'desc': "跨优先级边界",
            'start': (1, datetime(2024, 1, 2)),
            'end': (2, datetime(2024, 1, 1)),
            'op': "[]",
            'expected': {"task2", "task3"}
        },
        {
            'desc': "同优先级时间范围",
            'start': (1, datetime(2024, 1, 1)),
            'end': (1, datetime(2024, 1, 2)),
            'op': "[]",
            'expected': {"task1", "task2"}
        },
        {
            'desc': "开区间测试",
            'start': (1, datetime(2024, 1, 1)),
            'end': (2, datetime(2024, 1, 1)),
            'op': "()",
            'expected': {"task2"}
        },
        {
            'desc': "左闭右开测试",
            'start': (1, datetime(2024, 1, 1)),
            'end': (2, datetime(2024, 1, 1)),
            'op': "[)",
            'expected': {"task1", "task2"}
        },
        {
            'desc': "左开右闭测试",
            'start': (1, datetime(2024, 1, 1)),
            'end': (2, datetime(2024, 1, 1)),
            'op': "(]",
            'expected': {"task3"}
        }
    ]
    
    for case in test_cases:
        print(f"\n测试用例: {case['desc']}")
        print(f"范围: {case['op']} {case['start']} -> {case['end']}")
        
        # 打印比较过程
        print("\n比较过程:")
        for key in btree._tree.keys:
            start_cmp = btree._safe_compare(key, case['start'])
            end_cmp = btree._safe_compare(key, case['end'])
            print(f"键 {key}:")
            print(f"  与起始值比较: {start_cmp}")
            print(f"  与结束值比较: {end_cmp}")
        
        result = set(btree.query(case['op'], case['start'], case['end']))
        print(f"\n期望结果: {case['expected']}")
        print(f"实际结果: {result}")
        assert result == case['expected']

def test_edge_cases_detailed(btree):
    """详细测试边界值处理"""
    print("\n=== 开始测试边界值处理 ===")
    
    # 测试数据
    edge_cases = [
        (float('-inf'), "minus_inf", "负无穷"),
        (float('inf'), "plus_inf", "正无穷"),
        (None, "null_value", "空值"),
        ("", "empty_string", "空字符串"),
        (0, "zero", "零值")
    ]
    
    # 添加数据并验证
    for value, owner_id, desc in edge_cases:
        print(f"\n添加{desc}: {value} -> {owner_id}")
        btree.add(value, owner_id)
        print("当前树结构:")
        print(btree._debug_print_tree())
        
        # 验证添加后的查询
        result = btree.query("==", value)
        print(f"查询结果: {result}")
        assert owner_id in result
    
    # 测试特殊值的范围查询
    range_tests = [
        {
            'desc': "包含负无穷的范围",
            'start': float('-inf'),
            'end': 0,
            'expected': {"minus_inf", "zero"}
        },
        {
            'desc': "包含正无穷的范围",
            'start': 0,
            'end': float('inf'),
            'expected': {"zero", "plus_inf"}
        },
        {
            'desc': "空值处理",
            'start': None,
            'end': "",
            'expected': {"null_value", "empty_string"}
        }
    ]
    
    for test in range_tests:
        print(f"\n测试: {test['desc']}")
        print(f"范围: [{test['start']}, {test['end']}]")
        result = set(btree.query("[]", test['start'], test['end']))
        print(f"期望结果: {test['expected']}")
        print(f"实际结果: {result}")
        assert result == test['expected']

def test_large_dataset_performance_detailed(btree):
    """详细的大数据集性能测试"""
    print("\n=== 开始详细性能测试 ===")
    
    import time
    from statistics import mean, median
    
    # 测试参数
    n = 1000
    batch_size = 100
    query_samples = 10
    
    # 生成测试数据
    data = [(i, f"item{i}") for i in range(n)]
    
    # 批量插入性能
    batch_times = []
    for i in range(0, n, batch_size):
        batch = data[i:i+batch_size]
        start_time = time.time()
        for value, owner_id in batch:
            btree.add(value, owner_id)
        batch_time = time.time() - start_time
        batch_times.append(batch_time)
        print(f"批次 {i//batch_size + 1}: 插入 {batch_size} 条数据用时 {batch_time:.4f}秒")
    
    # 查询性能
    query_times = []
    for i in range(query_samples):
        start = n//4 * i // query_samples
        end = n//2 * (i + 1) // query_samples
        start_time = time.time()
        result = btree.query("[]", start, end)
        query_time = time.time() - start_time
        query_times.append(query_time)
        print(f"查询 [{start}, {end}] 用时: {query_time:.4f}秒")
    
    # 输出性能统计
    print("\n性能统计:")
    print(f"插入性能:")
    print(f"  总时间: {sum(batch_times):.4f}秒")
    print(f"  平均每批: {mean(batch_times):.4f}秒")
    print(f"  中位数: {median(batch_times):.4f}秒")
    print(f"查询性能:")
    print(f"  平均: {mean(query_times):.4f}秒")
    print(f"  中位数: {median(query_times):.4f}秒")

