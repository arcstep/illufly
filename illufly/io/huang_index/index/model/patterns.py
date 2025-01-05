from enum import Enum
from typing import Any
import re

class KeyPattern(Enum):
    """键模式枚举"""
    PREFIX_ID = "prefix:id"  
    PREFIX_ID_SUFFIX = "prefix:id:suffix"
    PREFIX_INFIX_ID = "prefix:infix:id"
    PREFIX_INFIX_ID_SUFFIX = "prefix:infix:id:suffix"
    PREFIX_PATH_VALUE = "prefix:path:value"
    PREFIX_INFIX_PATH_VALUE = "prefix:infix:path:value"
    
    @classmethod
    def is_valid_key(cls, key: str) -> bool:
        """判断键是否符合任一模式"""
        if isinstance(key, bytes):
            key = key.decode()
            
        patterns = [
            r'^[^:]+:[^:]+$',  # prefix:id
            r'^[^:]+:[^:]+:[^:]+$',  # prefix:id:suffix 或 prefix:infix:id
            r'^[^:]+:[^:]+:[^:]+:[^:]+$',  # prefix:infix:id:suffix 或 prefix:infix:path:value
        ]
        return any(re.match(p, key) for p in patterns)
        
    @classmethod
    def make_key(cls, pattern: 'KeyPattern', **kwargs) -> str:
        """构造键
        
        Args:
            pattern: 键模式
            **kwargs: 键组成部分
            
        Returns:
            构造的键
        """
        def sanitize(value: Any) -> str:
            """清理键值中的非法字符"""
            if value is None:
                return ''
            # 将冒号替换为下划线
            return str(value).replace(':', '_')
        
        parts = []
        
        if pattern == cls.PREFIX_ID:
            parts = [kwargs['prefix'], kwargs['id']]
        elif pattern == cls.PREFIX_ID_SUFFIX:
            parts = [kwargs['prefix'], kwargs['id'], kwargs['suffix']]
        elif pattern == cls.PREFIX_INFIX_ID:
            parts = [kwargs['prefix'], kwargs['infix'], kwargs['id']]
        elif pattern == cls.PREFIX_INFIX_ID_SUFFIX:
            parts = [kwargs['prefix'], kwargs['infix'], kwargs['id'], kwargs['suffix']]
        elif pattern == cls.PREFIX_PATH_VALUE:
            parts = [kwargs['prefix'], kwargs['path'], kwargs['value']]
        elif pattern == cls.PREFIX_INFIX_PATH_VALUE:
            parts = [kwargs['prefix'], kwargs['infix'], kwargs['path'], kwargs['value']]
            
        # 对每个部分进行清理
        parts = [sanitize(p) for p in parts]
        return ":".join(p for p in parts if p)
