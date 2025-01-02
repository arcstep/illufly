from functools import lru_cache
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional, Tuple
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

class ValueError(ValueError):
    """路径解析错误"""
    pass

class PathParser:
    """路径解析器"""
    
    def __init__(self):
        self.IDENTIFIER_PATTERN = re.compile(r'[a-zA-Z_][a-zA-Z0-9_]*')
        self.DICT_KEY_PATTERN = re.compile(r'\{([^}]+)\}')
        self.LIST_INDEX_PATTERN = re.compile(r'\[([0-9]+|\*)\]')
    
    @lru_cache(maxsize=1024)
    def validate_path(self, path: str) -> None:
        """验证路径语法"""
        logger.info(f"开始验证路径: '{path}'")
        
        if not path:
            logger.error("检测到空路径")
            raise ValueError("空路径")
        
        # 1. 检查花括号配对
        open_count = path.count('{')
        close_count = path.count('}')
        if open_count != close_count:
            logger.error(f"花括号不配对: 左括号={open_count}, 右括号={close_count}")
            if open_count > close_count:
                raise ValueError("未闭合的花括号")
            else:
                raise ValueError("意外的右花括号")
        
        # 2. 检查花括号内容
        for match in re.finditer(r'\{([^}]*)\}', path):
            key = match.group(1)
            logger.info(f"检查花括号内容: '{key}'")
            if not key:
                raise ValueError("空的花括号")
            if "'" in key or '"' in key:
                raise ValueError("带引号的键")
            if '{' in key or '}' in key:
                raise ValueError("嵌套的花括号")
        
        # 3. 检查方括号配对
        open_count = path.count('[')
        close_count = path.count(']')
        if open_count != close_count:
            if open_count > close_count:
                raise ValueError("未闭合的方括号")
            else:
                raise ValueError("意外的右方括号")
        
        # 4. 检查基本分隔符错误
        if '..' in path:
            raise ValueError("连续点号")
        
        # 5. 检查标识符格式
        cleaned_path = re.sub(r'\[[^\]]*\]', '', path)  # 移除所有方括号内容
        cleaned_path = re.sub(r'\{[^}]+\}', '', cleaned_path)  # 移除字典键
        
        parts = cleaned_path.split('.')
        for part in parts:
            if part and not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', part):
                raise ValueError("非法标识符")
        
        # 检查方括号内容
        for match in re.finditer(r'\[([^\]]*)\]', path):
            index = match.group(1)
            if not index:
                logger.error("检测到空的方括号")
                raise ValueError("空的方括号")  # 在验证阶段就检查空方括号
            if not (index.isdigit() or index == '*'):
                logger.error("检测到非法的列表索引")
                raise ValueError("非法的列表索引")
    
    def _parse_without_validation(self, path: str) -> Tuple[PathSegment, ...]:
        """内部解析方法，不包含验证"""
        segments = []
        remaining = path
        
        while remaining:
            matched = False
            logger.info(f"当前待解析部分: '{remaining}'")
            
            # 1. 尝试匹配标识符
            if match := re.match(self.IDENTIFIER_PATTERN, remaining):
                identifier = match.group(0)
                segments.append(PathSegment(
                    type=SegmentType.ATTRIBUTE,
                    value=identifier,
                    original=identifier
                ))
                remaining = remaining[len(identifier):]
                matched = True
            
            # 2. 尝试匹配字典键
            elif match := re.match(self.DICT_KEY_PATTERN, remaining):
                key = match.group(1)
                original = match.group(0)
                segments.append(PathSegment(
                    type=SegmentType.DICT_KEY,
                    value=key,
                    original=original,
                    access_method="bracket"
                ))
                remaining = remaining[len(original):]
                matched = True
            
            # 3. 尝试匹配列表索引
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
            
            # 4. 处理分隔符
            if remaining.startswith('.'):
                remaining = remaining[1:]
                matched = True
            
            if not matched:
                raise ValueError(f"无法解析路径段: '{remaining}'")
        
        return tuple(segments)
    
    @lru_cache(maxsize=1024)
    def parse(self, path: str) -> Tuple[PathSegment, ...]:
        """解析路径字符串为路径段列表"""
        try:
            logger.info(f"开始解析路径: '{path}'")
            # 先进行验证
            self.validate_path(path)
            logger.info("路径验证通过，开始解析")
            return self._parse_without_validation(path)
        except ValueError as e:
            logger.error(f"路径解析失败: {str(e)}")
            raise
    
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
