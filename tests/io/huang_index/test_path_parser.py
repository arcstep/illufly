import pytest
import time
import logging
from functools import lru_cache

from illufly.io.huang_index import PathParser, PathSegment, SegmentType

logger = logging.getLogger(__name__)

class TestPathParser:
    """测试路径解析器"""
    
    @pytest.fixture
    def parser(self):
        return PathParser()
    
    def test_valid_paths(self, parser):
        """测试有效路径"""
        valid_cases = [
            # 基本路径
            ("{data}", [
                PathSegment(type=SegmentType.MAPPING, value="data")
            ]),
            ("data", [
                PathSegment(type=SegmentType.ATTRIBUTE, value="data")
            ]),
            ("user_name", [
                PathSegment(type=SegmentType.ATTRIBUTE, value="user_name")
            ]),
            
            # 映射访问
            ("data{key}", [
                PathSegment(type=SegmentType.ATTRIBUTE, value="data"),
                PathSegment(type=SegmentType.MAPPING, value="key")
            ]),
            
            # 序列访问
            ("items[0]", [
                PathSegment(type=SegmentType.ATTRIBUTE, value="items"),
                PathSegment(type=SegmentType.SEQUENCE, value="0")
            ]),
            
            # 属性访问
            ("user.name", [
                PathSegment(type=SegmentType.ATTRIBUTE, value="user"),
                PathSegment(type=SegmentType.ATTRIBUTE, value="name")
            ]),
            
            # 混合访问
            ("users[0].profile{settings}", [
                PathSegment(type=SegmentType.ATTRIBUTE, value="users"),
                PathSegment(type=SegmentType.SEQUENCE, value="0"),
                PathSegment(type=SegmentType.ATTRIBUTE, value="profile"),
                PathSegment(type=SegmentType.MAPPING, value="settings")
            ])
        ]
        
        for path, expected_segments in valid_cases:
            segments = parser.parse(path)
            assert len(segments) == len(expected_segments), \
                f"路径 '{path}' 段数不匹配"
            for actual, expected in zip(segments, expected_segments):
                assert actual.type == expected.type, \
                    f"路径 '{path}' 段类型不匹配: 期望 {expected.type}, 实际 {actual.type}"
                assert actual.value == expected.value, \
                    f"路径 '{path}' 段值不匹配: 期望 {expected.value}, 实际 {actual.value}"
    
    def test_invalid_paths(self, parser):
        """测试无效路径"""
        invalid_cases = [
            ("", "空路径"),
            ("data{", "未闭合的花括号"),
            ("data}", "意外的右花括号"),
            ("data{}", "空的花括号"),
            ("data{key}{}", "空的花括号"),
            ("data{'key'}", "带引号的键"),
            ("data{key{nested}}", "嵌套的花括号"),
            ("data[", "未闭合的方括号"),
            ("data]", "意外的右方括号"),
            ("data[]", "列表索引必须是非负整数"),
            ("data..", "连续点号"),
            ("123data", "非法标识符"),
            ("data[abc]", "列表索引必须是非负整数"),
            ("data[-1]", "列表索引必须是非负整数"),
            ("items[1.5]", "列表索引必须是非负整数"),
        ]
        
        for path, expected_error in invalid_cases:
            with pytest.raises(ValueError, match=expected_error):
                parser.parse(path)
    
    def test_cache_performance(self, parser):
        """测试缓存性能提升"""
        test_paths = [
            "data{key}[0].items.name",
            "users[0].profile",
            "config{theme}",
            "matrix[123].rows[456]"
        ]
        
        logger.info("\n=== 缓存性能测试 ===")
        
        # 1. 冷启动性能（无缓存）
        cold_times = []
        for path in test_paths:
            start_time = time.perf_counter()
            result1 = parser.parse(path)
            parse_time = time.perf_counter() - start_time
            cold_times.append(parse_time)
            logger.info(f"\n路径: '{path}'")
            logger.info(f"首次解析: {parse_time:.6f}秒")
        
        # 2. 缓存命中性能
        warm_times = []
        for path in test_paths:
            start_time = time.perf_counter()
            result2 = parser.parse(path)
            parse_time = time.perf_counter() - start_time
            warm_times.append(parse_time)
            logger.info(f"缓存命中: {parse_time:.6f}秒")
            logger.info(f"性能提升: {(cold_times[len(warm_times)-1]/parse_time):.1f}倍")
        
        # 3. 汇总统计
        avg_cold = sum(cold_times) / len(cold_times)
        avg_warm = sum(warm_times) / len(warm_times)
        avg_speedup = avg_cold / avg_warm
        
        logger.info(f"\n=== 性能统计 ===")
        logger.info(f"平均首次解析时间: {avg_cold:.6f}秒")
        logger.info(f"平均缓存命中时间: {avg_warm:.6f}秒")
        logger.info(f"平均性能提升: {avg_speedup:.1f}倍")
        
        # 4. 验证缓存结果一致性
        for path in test_paths:
            result1 = parser.parse(path)
            result2 = parser.parse(path)
            assert result1 == result2, "缓存结果应该相同"
