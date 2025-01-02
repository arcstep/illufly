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
class PathTypeInfo:
    """路径类型信息 - 包含路径、类型名称、路径类型、类型信息、解析后的路径段等信息
    
    用于描述路径的访问类型和相关信息
    """
    path: str                                       # 路径
    type_name: str                                  # 类型名称
    path_type: PathType                            # 路径类型
    type_info: Any                                 # 类型信息对象
    is_tag_list: bool = False                      # 是否是标签列表
    max_tags: int = 100                           # 最大标签数
    description: str = ""                         # 描述信息
    parsed_segments: List[PathSegment] = field(default_factory=list)  # 解析后的路径段

    def __repr__(self) -> str:
        return (f"PathTypeInfo(path='{self.path}', type_name='{self.type_name}', "
                f"path_type={self.path_type}, is_tag_list={self.is_tag_list})")