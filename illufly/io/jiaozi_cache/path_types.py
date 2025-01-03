from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, List, Any
from .path_parser import PathSegment

class PathType(Enum):
    """路径类型枚举 - 表示路径的访问类型
    
    支持两种路径类型:
    - REVERSIBLE: 可以建立反向索引的类型
    - NOT_REVERSIBLE: 不可建立反向索引的类型
    """
    REVERSIBLE = auto()      # 可以建立反向索引的类型
    NOT_REVERSIBLE = auto()  # 不可建立反向索引的类型

@dataclass
class PathInfo:
    """路径信息"""
    path: str                      # 标准化路径
    type_name: str                 # 类型名称
    path_type: PathType            # 路径类型
    access_method: str             # 访问方法
    access_path: str               # 实际访问路径
