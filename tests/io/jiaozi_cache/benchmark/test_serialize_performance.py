import pytest
import json
import msgpack
import orjson
import rapidjson
import ujson
from datetime import datetime
from typing import Dict, Any, Callable
import zlib
import lz4.frame
import snappy

@pytest.fixture
def test_data():
    """生成接近 500K 的测试数据"""
    return {
        # 字符串数据 (约 200K)
        "text_data": {
            f"key_{i}": "hello world" * 100
            for i in range(200)
        },
        
        # 数值数据 (约 150K)
        "numeric_data": {
            f"series_{i}": list(range(1000))
            for i in range(20)
        },
        
        # 嵌套结构 (约 150K)
        "nested_data": {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "version": "1.0.0",
                "description": "Performance test data" * 100
            },
            "records": [
                {
                    "id": i,
                    "timestamp": datetime.now().isoformat(),
                    "values": list(range(100)),
                    "name": f"item_{i}" * 10,
                    "metadata": {
                        "type": "test",
                        "category": "benchmark",
                        "tags": ["test", "benchmark", "python"] * 10
                    }
                }
                for i in range(100)
            ]
        }
    }

@pytest.mark.benchmark(group="serialization")
@pytest.mark.parametrize("lib,dumps", [
    ("json", json.dumps),
    ("orjson", orjson.dumps),
    ("rapidjson", rapidjson.dumps),
    ("ujson", ujson.dumps),
    ("msgpack", lambda x: msgpack.packb(x, use_bin_type=True)),
])
def test_serialization(benchmark, lib: str, dumps: Callable, test_data: Dict):
    """测试序列化性能"""
    result = benchmark(dumps, test_data)
    size = len(result)
    benchmark.extra_info["size"] = size
    print(f"\n{lib}:")
    print(f"  序列化大小: {size:,} bytes")
    
    # 如果是第一个测试 (json)，保存基准大小
    if lib == "json":
        benchmark.extra_info["base_size"] = size
    else:
        base_size = benchmark.extra_info.get("base_size", size)
        diff = ((size - base_size) / base_size) * 100
        print(f"  与JSON相比: {diff:+.1f}%")

@pytest.mark.benchmark(group="deserialization")
@pytest.mark.parametrize("lib,dumps,loads", [
    ("json", json.dumps, json.loads),
    ("orjson", orjson.dumps, orjson.loads),
    ("rapidjson", rapidjson.dumps, rapidjson.loads),
    ("ujson", ujson.dumps, ujson.loads),
    ("msgpack", 
     lambda x: msgpack.packb(x, use_bin_type=True),
     lambda x: msgpack.unpackb(x, raw=False)),
])
def test_deserialization(benchmark, lib: str, dumps: Callable, loads: Callable, test_data: Dict):
    """测试反序列化性能"""
    serialized = dumps(test_data)
    size = len(serialized)
    benchmark.extra_info["size"] = size
    print(f"\n{lib}:")
    print(f"  序列化大小: {size:,} bytes")
    
    # 如果是第一个测试 (json)，保存基准大小
    if lib == "json":
        benchmark.extra_info["base_size"] = size
    else:
        base_size = benchmark.extra_info.get("base_size", size)
        diff = ((size - base_size) / base_size) * 100
        print(f"  与JSON相比: {diff:+.1f}%")
    
    benchmark(loads, serialized)

def test_data_size_verification(test_data):
    """验证测试数据的原始大小"""
    json_size = len(json.dumps(test_data))
    print(f"\n原始JSON大小: {json_size:,} bytes")
    assert json_size > 400_000, "测试数据应该接近 450K"

@pytest.mark.benchmark(group="compression")
@pytest.mark.parametrize("lib,dumps,compress", [
    ("json+zlib", json.dumps, lambda x: zlib.compress(x.encode() if isinstance(x, str) else x)),
    ("json+lz4", json.dumps, lambda x: lz4.frame.compress(x.encode() if isinstance(x, str) else x)),
    ("json+snappy", json.dumps, lambda x: snappy.compress(x.encode() if isinstance(x, str) else x)),
    ("msgpack+zlib", lambda x: msgpack.packb(x, use_bin_type=True), zlib.compress),
    ("msgpack+lz4", lambda x: msgpack.packb(x, use_bin_type=True), lz4.frame.compress),
    ("msgpack+snappy", lambda x: msgpack.packb(x, use_bin_type=True), snappy.compress),
])
def test_serialization_with_compression(benchmark, lib: str, dumps: Callable, compress: Callable, test_data: Dict):
    """测试序列化+压缩的性能"""
    def serialize_and_compress():
        serialized = dumps(test_data)
        return compress(serialized)
    
    result = benchmark(serialize_and_compress)
    size = len(result)
    print(f"\n{lib}:")
    print(f"  压缩后大小: {size:,} bytes")

def test_size_comparison(test_data):
    """比较不同格式的数据大小"""
    # 序列化
    json_data = json.dumps(test_data)
    orjson_data = orjson.dumps(test_data)
    rapidjson_data = rapidjson.dumps(test_data)
    ujson_data = ujson.dumps(test_data)
    msgpack_data = msgpack.packb(test_data, use_bin_type=True)
    
    # 计算大小
    sizes = {
        "json": len(json_data),
        "orjson": len(orjson_data),
        "rapidjson": len(rapidjson_data),
        "ujson": len(ujson_data),
        "msgpack": len(msgpack_data)
    }
    
    # 以 JSON 为基准计算差异
    base_size = sizes["json"]
    print("\n序列化后的数据大小比较:")
    print(f"{'格式':12} {'大小(bytes)':>12} {'与JSON相比':>12}")
    print("-" * 40)
    
    for name, size in sizes.items():
        diff = ((size - base_size) / base_size) * 100
        print(f"{name:12} {size:>12,d} {diff:>+11.1f}%")
    
    # 测试压缩后的大小
    print("\n压缩后的数据大小比较:")
    print(f"{'格式':12} {'大小(bytes)':>12} {'与JSON相比':>12}")
    print("-" * 40)
    
    compressed_sizes = {
        "json+zlib": len(zlib.compress(json_data.encode())),
        "orjson+zlib": len(zlib.compress(orjson_data)),
        "rapidjson+zlib": len(zlib.compress(rapidjson_data.encode())),
        "ujson+zlib": len(zlib.compress(ujson_data.encode())),
        "msgpack+zlib": len(zlib.compress(msgpack_data))
    }
    
    base_compressed = compressed_sizes["json+zlib"]
    for name, size in compressed_sizes.items():
        diff = ((size - base_compressed) / base_compressed) * 100
        print(f"{name:12} {size:>12,d} {diff:>+11.1f}%")