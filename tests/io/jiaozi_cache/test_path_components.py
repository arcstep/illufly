import pytest
from illufly.io.jiaozi_cache.path_parser import PathParser, PathSegment, SegmentType
from illufly.io.jiaozi_cache.object_types import TypeHandler, DictHandler, PathType, TypeInfo
from illufly.io.jiaozi_cache import ObjectPathRegistry, PathTypeInfo, PathType, PathNotFoundError, PathValidationError, PathTypeError

class TestPathParser:
    """测试路径解析器"""
    
    @pytest.fixture
    def parser(self):
        return PathParser()
    
    def test_simple_attribute_paths(self, parser):
        """测试简单属性路径"""
        cases = [
            ("user.name", [
                PathSegment(type=SegmentType.ATTRIBUTE, value="user", original="user"),
                PathSegment(type=SegmentType.ATTRIBUTE, value="name", original="name")
            ]),
            ("profile.address.city", [
                PathSegment(type=SegmentType.ATTRIBUTE, value="profile", original="profile"),
                PathSegment(type=SegmentType.ATTRIBUTE, value="address", original="address"),
                PathSegment(type=SegmentType.ATTRIBUTE, value="city", original="city")
            ])
        ]
        self._verify_path_cases(parser, cases)
    
    def test_dict_access_paths(self, parser):
        """测试字典访问路径"""
        cases = [
            ("data{key}", [
                PathSegment(type=SegmentType.ATTRIBUTE, value="data", original="data"),
                PathSegment(type=SegmentType.DICT_KEY, value="key", original="{key}", 
                          access_method="bracket")
            ]),
            ("config{settings}{theme}", [
                PathSegment(type=SegmentType.ATTRIBUTE, value="config", original="config"),
                PathSegment(type=SegmentType.DICT_KEY, value="settings", original="{settings}", 
                          access_method="bracket"),
                PathSegment(type=SegmentType.DICT_KEY, value="theme", original="{theme}", 
                          access_method="bracket")
            ])
        ]
        self._verify_path_cases(parser, cases)
    
    def test_list_access_paths(self, parser):
        """测试列表访问路径"""
        cases = [
            ("items[0]", [
                PathSegment(type=SegmentType.ATTRIBUTE, value="items", original="items"),
                PathSegment(type=SegmentType.LIST_INDEX, value="0", original="[0]", access_method="bracket")
            ]),
            ("data[*]", [
                PathSegment(type=SegmentType.ATTRIBUTE, value="data", original="data"),
                PathSegment(type=SegmentType.LIST_INDEX, value="*", original="[*]", is_wildcard=True, access_method="bracket")
            ])
        ]
        self._verify_path_cases(parser, cases)
    
    def test_mixed_access_paths(self, parser):
        """测试混合访问路径"""
        cases = [
            ("users[0].profile.name", [
                PathSegment(type=SegmentType.ATTRIBUTE, value="users", original="users"),
                PathSegment(type=SegmentType.LIST_INDEX, value="0", original="[0]", 
                          access_method="bracket"),
                PathSegment(type=SegmentType.ATTRIBUTE, value="profile", original="profile"),
                PathSegment(type=SegmentType.ATTRIBUTE, value="name", original="name")
            ]),
            ("data{config}[0].items[*].name", [
                PathSegment(type=SegmentType.ATTRIBUTE, value="data", original="data"),
                PathSegment(type=SegmentType.DICT_KEY, value="config", original="{config}", 
                          access_method="bracket"),
                PathSegment(type=SegmentType.LIST_INDEX, value="0", original="[0]", 
                          access_method="bracket"),
                PathSegment(type=SegmentType.ATTRIBUTE, value="items", original="items"),
                PathSegment(type=SegmentType.LIST_INDEX, value="*", original="[*]", 
                          is_wildcard=True, access_method="bracket"),
                PathSegment(type=SegmentType.ATTRIBUTE, value="name", original="name")
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

class TestDictHandler:
    """测试字典处理器"""
    
    @pytest.fixture
    def handler(self):
        return DictHandler()
    
    @pytest.fixture
    def sample_dict(self):
        return {
            "name": "test",
            "value": 42,
            "nested": {
                "x": 10,
                "y": 20
            },
            "list": [1, 2, 3],
            "complex": {
                "items": [
                    {"id": 1, "tags": ["a", "b"]},
                    {"id": 2, "tags": ["c", "d"]}
                ]
            }
        }
    
    def test_get_paths(self, handler, sample_dict):
        """测试路径生成"""
        paths = handler.get_paths(sample_dict)
        expected_paths = {
            "",                     # 根路径
            "{name}",              # 简单键
            "{value}",
            "{nested}",            # 嵌套字典
            "{nested}{x}",
            "{nested}{y}",
            "{list}",              # 列表
            "{complex}",           # 复杂嵌套
            "{complex}{items}"     # 列表类型的字段
            # 注意：不应该包含列表索引的路径，因为这应该由 ListHandler 处理
        }
        assert {p[0] for p in paths} == expected_paths
    
    def test_nested_dict_paths(self, handler):
        """测试纯字典嵌套的路径生成"""
        nested_dict = {
            "settings": {
                "theme": {
                    "primary": "blue",
                    "secondary": "gray"
                }
            }
        }
        paths = handler.get_paths(nested_dict)
        expected_paths = {
            "",
            "{settings}",
            "{settings}{theme}",
            "{settings}{theme}{primary}",
            "{settings}{theme}{secondary}"
        }
        assert {p[0] for p in paths} == expected_paths

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