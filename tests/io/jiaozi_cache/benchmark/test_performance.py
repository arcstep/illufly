import pytest
import time
import random
import logging
from typing import Dict, Any
from statistics import mean, median
from pathlib import Path

from illufly.io.jiaozi_cache.store import CachedJSONStorage

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PerformanceTester:
    def __init__(self, storage: CachedJSONStorage):
        self.storage = storage
        self.results: Dict[str, list] = {
            "write_times": [],
            "read_times": [],
            "cache_hit_times": [],
            "cache_miss_times": []
        }

    def measure_write(self, key: str, value: Any) -> float:
        start = time.perf_counter()
        self.storage.set(key, value)
        duration = time.perf_counter() - start
        self.results["write_times"].append(duration)
        return duration

    def measure_read(self, key: str) -> float:
        start = time.perf_counter()
        self.storage.get(key)
        duration = time.perf_counter() - start
        return duration

    def run_benchmark(self, num_operations: int = 1000):
        print("\n" + "="*50)
        print("开始性能测试...")
        print("="*50 + "\n")
        
        # 1. 写入测试
        print("执行写入测试中...")
        for i in range(num_operations):
            data = {"value": i, "data": "x" * 100}
            self.measure_write(f"key_{i}", data)
            if i % 100 == 0:
                print(f"已完成 {i}/{num_operations} 写入操作")

        # 2. 读取测试
        print("\n执行读取测试中...")
        for i in range(num_operations):
            if random.random() < 0.2:
                key = f"nonexistent_key_{random.randint(0, 1000)}"
            else:
                key = f"key_{random.randint(0, num_operations-1)}"
            
            duration = self.measure_read(key)
            if i % 100 == 0:
                print(f"已完成 {i}/{num_operations} 读取操作")
            
            if self.storage._cache.get(key) is not None:
                self.results["cache_hit_times"].append(duration)
            else:
                self.results["cache_miss_times"].append(duration)

    def generate_report(self) -> str:
        report = ["\n性能测试报告", "=" * 50]
        
        # 1. 写入性能
        write_times = self.results["write_times"]
        report.extend([
            "\n写入性能:",
            f"- 总写入操作: {len(write_times)}",
            f"- 平均写入时间: {mean(write_times)*1000:.3f}ms",
            f"- 中位数写入时间: {median(write_times)*1000:.3f}ms",
            f"- 最快写入: {min(write_times)*1000:.3f}ms",
            f"- 最慢写入: {max(write_times)*1000:.3f}ms"
        ])

        # 2. 读取性能
        hits = self.results["cache_hit_times"]
        misses = self.results["cache_miss_times"]
        total_reads = len(hits) + len(misses)
        
        if total_reads > 0:
            hit_rate = len(hits) / total_reads * 100
            report.extend([
                "\n读取性能:",
                f"- 总读取操作: {total_reads}",
                f"- 缓存命中率: {hit_rate:.1f}%",
                f"- 缓存命中平均时间: {mean(hits)*1000:.3f}ms",
                f"- 缓存未命中平均时间: {mean(misses)*1000:.3f}ms" if misses else "无缓存未命中"
            ])

        # 3. 缓存效果
        if misses:
            speedup = mean(misses) / mean(hits)
            report.append(f"\n- 缓存读取加速比: {speedup:.1f}x")

        # 4. 内存使用
        metrics = self.storage.get_metrics()
        report.extend([
            "\n资源使用:",
            f"- 读缓存大小: {metrics['read_cache']['size']}",
            f"- 写缓冲大小: {metrics['write_buffer']['size']}",
            f"- 读缓存命中次数: {metrics['read_cache']['hits']}",
            f"- 读缓存未命中次数: {metrics['read_cache']['misses']}"
        ])

        return "\n".join(report)

@pytest.mark.performance
def test_performance(tmp_path):
    """性能基准测试"""
    # 创建测试存储，使用正确的参数名称
    storage = CachedJSONStorage[Dict](
        data_dir=str(tmp_path),
        segment="perf_test.json",
        cache_size=500,  # 改为 cache_size
        flush_threshold=100  # 改为 flush_threshold
    )
    
    try:
        # 运行基准测试
        tester = PerformanceTester(storage)
        tester.run_benchmark(num_operations=1000)
        
        # 打印详细报告
        print(tester.generate_report())
        print("\n" + "="*50)
        
        # 基本断言
        metrics = storage.get_metrics()
        assert metrics["read_cache"]["hits"] > 0
        
        if tester.results["cache_miss_times"]:
            assert mean(tester.results["cache_hit_times"]) < mean(tester.results["cache_miss_times"])
        else:
            assert mean(tester.results["cache_hit_times"]) < 0.1
            
    finally:
        storage.close()

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"]) 