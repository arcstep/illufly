from typing import List
from .path_parser import PathSegment, SegmentType

class PathMatcher:
    """路径匹配器"""
    
    def match(self, path: List[PathSegment], pattern: List[PathSegment]) -> bool:
        """检查路径是否匹配模式"""
        if len(path) != len(pattern):
            return False
            
        return all(self._match_segment(p, pat) for p, pat in zip(path, pattern))
    
    def _match_segment(self, segment: PathSegment, pattern: PathSegment) -> bool:
        """匹配单个路径段"""
        # 类型必须匹配
        if segment.type != pattern.type:
            return False
            
        # 通配符模式总是匹配
        if pattern.is_wildcard or pattern.value == '*':
            return True
            
        # 精确匹配值
        return segment.value == pattern.value 