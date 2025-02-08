from functools import lru_cache
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional, Tuple
import re
import logging

logger = logging.getLogger(__name__)

# 路径语法关键字
PATH_SYNTAX = {
    'ATTRIBUTE_SEPARATOR': '.',    # 属性访问分隔符
    'SEQUENCE_START': '[',         # 序列访问开始
    'SEQUENCE_END': ']',          # 序列访问结束
    'MAPPING_START': '{',         # 映射访问开始
    'MAPPING_END': '}',          # 映射访问结束
}

# 特殊字符模式（用于规范化）
SPECIAL_CHARS = frozenset([
    PATH_SYNTAX['ATTRIBUTE_SEPARATOR'],
    PATH_SYNTAX['SEQUENCE_START'],
    PATH_SYNTAX['SEQUENCE_END'],
    PATH_SYNTAX['MAPPING_START'],
    PATH_SYNTAX['MAPPING_END']
])

class SegmentType(Enum):
    """路径段类型
    
    支持三种基本访问操作：
    - ATTRIBUTE: 对象属性访问，使用点号(.)，如 user.name
    - SEQUENCE: 序列索引访问，使用方括号([])，如 items[0]
    - MAPPING: 映射键访问，使用花括号({})，如 data{key}
    """
    ATTRIBUTE = auto()  # 属性访问，如 .name
    SEQUENCE = auto()   # 序列索引，如 [0]
    MAPPING = auto()    # 映射键，如 {key}

@dataclass
class PathSegment:
    """路径段 - 表示路径中的一个访问操作
    
    每个路径段代表一个具体的访问操作，支持三种类型：
    1. 属性访问：使用点号(.)访问对象属性
       示例：user.name -> ATTRIBUTE("name")
       
    2. 列表索引：使用方括号([])访问列表元素
       示例：items[0] -> SEQUENCE("0")
       
    3. 字典键访问：使用花括号({})访问字典值
       示例：data{key} -> MAPPING("key")
    
    Attributes:
        type: 段类型，指示访问操作的类型
        value: 段的值，可能是属性名、索引值或键名
    """
    type: SegmentType
    value: str

class PathParser:
    """路径解析器 - 将路径字符串解析为路径段序列
    
    支持的路径语法：
    1. 属性访问：使用点号
       user.name
       profile.address.city
    
    2. 列表索引：使用方括号 + 非负整数
       items[0]
       users[1].addresses[0]
    
    3. 字典键访问：使用花括号
       data{key}
       config{theme}.value
    
    4. 复合访问：支持任意组合
       users[0].profile{settings}.addresses[1].city
    
    注意事项：
    - 列表索引必须是非负整数
    - 字典键不支持引号和嵌套花括号
    - 属性名必须是有效的标识符
    """
    
    def __init__(self):
        """初始化解析器，编译正则表达式模式"""
        self.IDENTIFIER_PATTERN = re.compile(r'[a-zA-Z_][a-zA-Z0-9_]*')
        self.DICT_KEY_PATTERN = re.compile(r'\{([^}]+)\}')
        self.LIST_INDEX_PATTERN = re.compile(r'\[([0-9]+)\]')
    
    @lru_cache(maxsize=1024)
    def validate_path(self, path: str) -> None:
        """验证路径语法的有效性
        
        执行以下验证：
        1. 检查路径非空
        2. 验证花括号配对和内容
        3. 验证方括号配对和索引格式
        4. 检查分隔符使用
        5. 验证标识符格式
        
        Args:
            path: 要验证的路径字符串
            
        Raises:
            ValueError: 当路径语法无效时，提供具体的错误信息
        """

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
        
        # 6. 检查方括号内容必须是数字
        for match in re.finditer(r'\[([^\]]*)\]', path):
            index = match.group(1)
            if not index.isdigit():
                raise ValueError(f"列表索引必须是非负整数，而不是 '{index}'")
    
    def _parse_without_validation(self, path: str) -> Tuple[PathSegment, ...]:
        """内部解析方法，将已验证的路径字符串解析为路径段
        
        按顺序尝试匹配以下模式：
        1. 标识符（属性访问）
        2. 字典键访问
        3. 列表索引访问
        4. 分隔符处理
        
        Args:
            path: 已通过验证的路径字符串
            
        Returns:
            Tuple[PathSegment, ...]: 解析后的路径段元组
            
        Raises:
            ValueError: 当遇到无法解析的路径段时
        """
        segments = []
        remaining = path
        
        while remaining:
            matched = False
            
            # 1. 尝试匹配标识符
            if match := re.match(self.IDENTIFIER_PATTERN, remaining):
                identifier = match.group(0)
                segments.append(PathSegment(
                    type=SegmentType.ATTRIBUTE,
                    value=identifier
                ))
                remaining = remaining[len(identifier):]
                matched = True
            
            # 2. 尝试匹配字典键
            elif match := re.match(self.DICT_KEY_PATTERN, remaining):
                key = match.group(1)
                original = match.group(0)
                segments.append(PathSegment(
                    type=SegmentType.MAPPING,
                    value=key
                ))
                remaining = remaining[len(original):]
                matched = True
            
            # 3. 尝试匹配列表索引
            elif match := re.match(self.LIST_INDEX_PATTERN, remaining):
                index = match.group(1)
                original = match.group(0)
                segments.append(PathSegment(
                    type=SegmentType.SEQUENCE,
                    value=index
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
        """解析路径字符串为路径段序列
        
        完整的解析流程：
        1. 验证路径语法
        2. 解析为路径段序列
        3. 缓存结果（使用 lru_cache）
        
        Args:
            path: 要解析的路径字符串
            
        Returns:
            Tuple[PathSegment, ...]: 解析后的路径段元组
            
        Raises:
            ValueError: 当路径语法无效或解析失败时
            
        Example:
            >>> parser = PathParser()
            >>> segments = parser.parse("users[0].profile{settings}")
            >>> [seg.type.name for seg in segments]
            ['ATTRIBUTE', 'SEQUENCE', 'ATTRIBUTE', 'MAPPING']
        """
        try:
            # 先进行验证
            self.validate_path(path)
            return self._parse_without_validation(path)
        except ValueError as e:
            logger.error(f"路径解析失败: {str(e)}")
            raise

    @staticmethod
    def is_safe_for_path(value: str) -> bool:
        """检查值是否安全用于构建路径
        
        检查值中是否包含路径语法的保留字符 (.{}[])。
        这些字符会影响路径解析，因此不应该出现在对象的属性名中。
        
        Args:
            value: 要检查的值
            
        Returns:
            bool: 如果值不包含任何保留字符则返回 True
            
        Examples:
            >>> PathParser.is_safe_for_path("user_name")     # True
            >>> PathParser.is_safe_for_path("name.first")    # False
            >>> PathParser.is_safe_for_path("items[0]")      # False
            >>> PathParser.is_safe_for_path("config{key}")   # False
        """
        return not bool(set(value) & SPECIAL_CHARS)
