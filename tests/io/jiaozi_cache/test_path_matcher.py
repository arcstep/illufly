import pytest
from illufly.io.jiaozi_cache.path_parser import PathParser, PathSegment, SegmentType
from illufly.io.jiaozi_cache.path_matcher import PathMatcher

class TestPathMatcher:
    """测试路径匹配器"""
    
    @pytest.fixture
    def matcher(self):
        return PathMatcher()
        
    @pytest.fixture
    def parser(self):
        return PathParser()
    
    @pytest.mark.parametrize("path,pattern,expected", [
        # 基本匹配
        ("name", "name", True),
        ("user.name", "user.name", True),
        ("items[0]", "items[0]", True),
        ("data{key}", "data{key}", True),
        
        # 通配符匹配
        ("items[0]", "items[*]", True),
        ("users[0].name", "users[*].name", True),
        ("data{key}", "data{*}", True),
        ("config.theme.color", "config.theme.color", True),
        
        # 不匹配
        ("name", "age", False),
        ("items[0]", "items[1]", False),
        ("data{key1}", "data{key2}", False),
        ("user.name", "user.age", False),

        # 复杂路径匹配
        ("users[0].profile.name", "users[*].profile.name", True),
        ("data{config}[0].items", "data{*}[*].items", True),
        ("matrix[0].rows[1]", "matrix[*].rows[*]", True),
        
        # 长度不匹配
        ("user", "user.name", False),
        ("user.name.first", "user.name", False),
    ])
    def test_path_matching(self, matcher, parser, path, pattern, expected):
        """测试路径匹配"""
        path_segments = parser.parse(path)
        pattern_segments = parser.parse(pattern)
        assert matcher.match(path_segments, pattern_segments) == expected 