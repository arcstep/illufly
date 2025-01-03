import pytest
from illufly.io.jiaozi_cache.path_parser import PathParser, PathSegment, SegmentType
import time
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

class TestPathParser:
    """测试路径解析器"""
    
    @pytest.fixture
    def parser(self):
        return PathParser()
    
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
            ("data[]", "空的方括号"),
            ("data..", "连续点号"),
            ("123data", "非法标识符"),
            ("data[abc]", "非法的列表索引"),  # 列表索引必须是数字或 *
        ]
        
        for path, expected_error in invalid_cases:
            with pytest.raises(ValueError, match=expected_error):
                parser.parse(path)
    
    def test_valid_paths(self, parser):
        """测试有效路径"""
        valid_cases = [
            # 基本路径
            "data",
            "user_name",
            "_private",
            
            # 字典访问
            "data{key}",
            "config{setting}",
            "data{key_123}",
            
            # 列表访问
            "items[0]",
            "data[*]",
            "matrix[123]",
            
            # 属性访问
            "user.name",
            "profile.address.city",
            
            # 混合访问
            "data[0].items",
            "users[*].name",
            "data{key}[0]",
            "config{theme}.color",
            "data[0]{key}",
            "items[0].data{key}[1]"
        ]
        
        for path in valid_cases:
            try:
                parser.parse(path)
            except ValueError as e:
                pytest.fail(f"路径 '{path}' 应该是有效的，但抛出了异常: {str(e)}")
    
    def test_cache_performance(self, parser):
        """测试缓存性能提升"""
        # 准备测试路径
        test_paths = [
            "data{key}[0].items[*].name",  # 复杂路径
            "users[0].profile",            # 中等复杂度
            "config{theme}",               # 简单路径
            "matrix[123].rows[*]"          # 数组访问
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
            assert result1 is result2, "缓存结果应该是同一个对象"

def test_path_segment_equality():
    """测试PathSegment相等性"""
    seg1 = PathSegment(type=SegmentType.ATTRIBUTE, value="name", original="name")
    seg2 = PathSegment(type=SegmentType.ATTRIBUTE, value="name", original="name")
    seg3 = PathSegment(type=SegmentType.LIST_INDEX, value="0", original="[0]")
    
    assert seg1 == seg2
    assert seg1 != seg3 

class TestComplexPathParser:
    """测试复杂路径解析"""
    
    @pytest.fixture
    def parser(self):
        return PathParser()
    
    def test_dict_access_paths(self, parser):
        """测试字典访问路径"""
        cases = [
            ("data{key}", [
                PathSegment(type=SegmentType.ATTRIBUTE, value="data", original="data"),
                PathSegment(type=SegmentType.DICT_KEY, value="key", original="{key}", 
                          access_method="bracket")
            ]),
            ("config{theme}{colors}", [
                PathSegment(type=SegmentType.ATTRIBUTE, value="config", original="config"),
                PathSegment(type=SegmentType.DICT_KEY, value="theme", original="{theme}", 
                          access_method="bracket"),
                PathSegment(type=SegmentType.DICT_KEY, value="colors", original="{colors}", 
                          access_method="bracket")
            ])
        ]
        self._verify_path_cases(parser, cases)
    
    def test_mixed_nested_paths(self, parser):
        """测试混合嵌套路径（字典、列表、属性）"""
        cases = [
            ("users[0].profile{settings}", [  # 列表用[]，字典用{}，类属性用.
                PathSegment(type=SegmentType.ATTRIBUTE, value="users", original="users"),
                PathSegment(type=SegmentType.LIST_INDEX, value="0", original="[0]", 
                          access_method="bracket"),
                PathSegment(type=SegmentType.ATTRIBUTE, value="profile", original="profile"),
                PathSegment(type=SegmentType.DICT_KEY, value="settings", original="{settings}", 
                          access_method="bracket")
            ]),
            ("data{config}[0].items{metadata}", [
                PathSegment(type=SegmentType.ATTRIBUTE, value="data", original="data"),
                PathSegment(type=SegmentType.DICT_KEY, value="config", original="{config}", 
                          access_method="bracket"),
                PathSegment(type=SegmentType.LIST_INDEX, value="0", original="[0]", 
                          access_method="bracket"),
                PathSegment(type=SegmentType.ATTRIBUTE, value="items", original="items"),
                PathSegment(type=SegmentType.DICT_KEY, value="metadata", original="{metadata}", 
                          access_method="bracket")
            ])
        ]
        self._verify_path_cases(parser, cases)
    
    def _verify_path_cases(self, parser, cases):
        """验证路径解析用例"""
        for path, expected_segments in cases:
            segments = parser.parse(path)
            assert len(segments) == len(expected_segments), \
                f"路径 '{path}' 段数不匹配: 期望 {len(expected_segments)}, 实际 {len(segments)}"
            for actual, expected in zip(segments, expected_segments):
                assert actual == expected, \
                    f"路径 '{path}' 段不匹配:\n期望: {expected}\n实际: {actual}" 
