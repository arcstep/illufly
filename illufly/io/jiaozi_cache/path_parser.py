from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional
import re
import logging

logger = logging.getLogger(__name__)

class SegmentType(Enum):
    """路径段类型"""
    ATTRIBUTE = auto()  # 属性访问，如 .name
    LIST_INDEX = auto() # 列表索引，如 [0]
    DICT_KEY = auto()   # 字典键，如 {key}
    WILDCARD = auto()   # 通配符，如 [*] 或 {*}

@dataclass
class PathSegment:
    """路径段 - 表示路径中的一个访问操作
    
    用于表示路径字符串中的一个访问操作，支持:
    - 属性访问: user.name -> ATTRIBUTE("name")
    - 列表索引: items[0] -> LIST_INDEX("0") 
    - 字典键访问: data{key} -> DICT_KEY("key")
    - 通配符: items[*] -> LIST_INDEX("*", is_wildcard=True)
    
    Attributes:
        type: 段类型(ATTRIBUTE/LIST_INDEX/DICT_KEY)
        value: 段的值(属性名/索引值/键名)
        original: 原始字符串表示
        is_wildcard: 是否是通配符
        access_method: 记录访问方式 ("dot" 或 "bracket")
    """
    type: SegmentType
    value: str
    original: str
    is_wildcard: bool = False
    access_method: str = "dot"  # 新增: 记录访问方式 ("dot" 或 "bracket")

class PathParser:
    """路径解析器"""
    
    # 修改正则表达式
    IDENTIFIER_PATTERN = re.compile(r'[a-zA-Z_][a-zA-Z0-9_]*')  # 移除 ^，允许在任何位置匹配
    DICT_KEY_PATTERN = re.compile(r'\{([^}]+)\}')
    LIST_INDEX_PATTERN = re.compile(r'\[([^\]]+)\]')
    
    def parse(self, path: str) -> List[PathSegment]:
        """解析路径字符串为路径段列表"""
        logger.info(f"开始解析路径: '{path}'")
        segments = []
        remaining = path
        
        while remaining:
            logger.info(f"当前待解析部分: '{remaining}'")
            matched = False
            
            # 1. 处理属性访问
            if match := re.match(self.IDENTIFIER_PATTERN, remaining):  # 仍然使用 match 从开头匹配
                identifier = match.group(0)
                segments.append(PathSegment(
                    type=SegmentType.ATTRIBUTE,
                    value=identifier,
                    original=identifier,
                    access_method="dot"
                ))
                remaining = remaining[len(identifier):]
                matched = True
            
            # 2. 处理字典键访问
            elif match := re.match(self.DICT_KEY_PATTERN, remaining):
                key = match.group(1)
                original = match.group(0)
                segments.append(PathSegment(
                    type=SegmentType.DICT_KEY,
                    value=key,
                    original=original,
                    is_wildcard=key == '*',
                    access_method="bracket"
                ))
                remaining = remaining[len(original):]
                matched = True
            
            # 3. 处理列表索引访问
            elif match := re.match(self.LIST_INDEX_PATTERN, remaining):
                index = match.group(1)
                original = match.group(0)
                segments.append(PathSegment(
                    type=SegmentType.LIST_INDEX,
                    value=index,
                    original=original,
                    is_wildcard=index == '*',
                    access_method="bracket"
                ))
                remaining = remaining[len(original):]
                matched = True
            
            # 处理分隔符
            if remaining.startswith('.'):
                remaining = remaining[1:]
                matched = True
            
            if not matched:
                raise ValueError(f"无法解析路径段: '{remaining}'")
        
        return segments
    
    def _find_identifier_end(self, text: str) -> int:
        """查找标识符结束位置"""
        for i, char in enumerate(text):
            if char in '.[':
                return i
        return len(text)
    
    def join_segments(self, segments: List[PathSegment]) -> str:
        """将路径段列表连接为路径字符串"""
        result = []
        for i, segment in enumerate(segments):
            if segment.type == SegmentType.LIST_INDEX:
                result.append(segment.original)
            elif i > 0 and segment.access_method == 'dot':
                result.append(f".{segment.value}")
            else:
                result.append(segment.value)
        return ''.join(result)
    
    def normalize_to_wildcard(self, segments: List[PathSegment]) -> List[PathSegment]:
        """将路径段列表中的具体索引/键转换为通配符形式"""
        normalized = []
        for segment in segments:
            if segment.type == SegmentType.LIST_INDEX and not segment.is_wildcard:
                normalized.append(PathSegment(
                    type=SegmentType.LIST_INDEX,
                    value='*',
                    original='[*]',
                    is_wildcard=True,
                    access_method='bracket'
                ))
            elif segment.type == SegmentType.DICT_KEY and not segment.is_wildcard:
                normalized.append(PathSegment(
                    type=segment.type,  # 保持原始类型
                    value='*',
                    original='*',
                    is_wildcard=True,
                    access_method=segment.access_method  # 保持原始访问方式
                ))
            else:
                normalized.append(segment)
        return normalized
