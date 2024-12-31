from typing import Dict, Any, List, Callable, Optional, Union, Tuple, Protocol, runtime_checkable, Type, Set
from abc import ABC, abstractmethod
import logging
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel
from collections.abc import Sequence
from collections import defaultdict
import re
import decimal

from ....config import get_env
from .index_config import IndexConfig

@runtime_checkable
class Indexable(Protocol):
    """可索引对象协议
    
    实现此协议的对象可以自定义其索引键生成方式。
    """
    def to_index_key(self) -> str:
        """生成用于索引的键
        
        Returns:
            str: 索引键
            
        Example:
            >>> class User:
            ...     def __init__(self, name: str, age: int):
            ...         self.name = name
            ...         self.age = age
            ...     
            ...     def to_index_key(self) -> str:
            ...         return f"{self.name}_{self.age}"
        """
        pass

class IndexError(Exception):
    """索引操作异常"""
    pass

class IndexBackend(ABC):
    """索引后端基类
    
    本类实现了对各种数据类型的索引支持，遵循以下设计原则：
    
    1. 索引目标支持：
        - 简单对象：str, int, float, bool, datetime, Decimal 等基本类型
        - 复杂结构：
            - 字典：通过点号访问嵌套字段
            - 列表/元组：通过数字索引访问元素
            - Pydantic 模型：直接访问属性
            - 实现了 Indexable 协议的自定义对象
        - Pydantic 模型：
            - 支持作为根对象索引
            - 支持作为字段值索引
            - 支持嵌套模型的字段索引
            - 支持模型字段的类型验证

    2. 索引值要求：
        - 常规索引值：
        - 仅接受简单类型作为索引值：str, int, float, bool, datetime, Decimal
        - 复杂对象必须通过 Indexable 协议自定义索引值生成
        - 支持单值查询和多值查询（AND/OR 模式）
        - Pydantic 模型：
            - 作为根对象时：
            - 使用 model_dump_json() 序列化后的 JSON 字符串进行精确匹配
            - 要求查询模型与索引模型的字段值完全相同
            - 不支持部分字段匹配，部分匹配请使用字段路径查询
            - 作为字段值时：
            - 同样使用序列化 JSON 进行匹配
            - 建议使用具体字段路径进行查询，而不是整个模型对象
        - 标签索引值：
            - 字段类型必须声明为 List[str]
            - 每个标签必须是非空字符串
            - 支持单个或多个标签查询（AND/OR 模式）

    3. 索引路径语法：
        - 基本语法：使用点号（.）分隔嵌套属性
        - 字典访问：
            - "user.name" -> user["name"]
            - "user.address.city" -> user["address"]["city"]
        - 列表访问：
            - "items.0" -> items[0]
            - "items.0.name" -> items[0]["name"]
        - 特殊路径：
            - "." -> 根对象
            - "tags" -> 直接字段
        - Pydantic 模型访问：
            - 根对象：
                "." -> 整个模型对象
            - 直接字段：
                "name" -> model.name
                "age" -> model.age
            - 嵌套模型：
                "address.city" -> model.address.city
                "address.location.latitude" -> model.address.location.latitude
            - 模型列表：
                "items.0.name" -> model.items[0].name
                "addresses.1.city" -> model.addresses[1].city
            - 复杂嵌套：
                "company.departments.0.employees.1.address.city" ->
                model.company.departments[0].employees[1].address.city

    4. 查询示例：
        - 根对象完全匹配：
        ```python
        # 索引时
        user1 = User(name="Alice", age=25)
        backend.update_index(user1, "user1")
        
        # 查询时
        query = User(name="Alice", age=25)  # 必须完全相同
        results = backend.find_with_root_object(query)  # 返回 ["user1"]
        
        # 部分字段不同则无法匹配
        query2 = User(name="Alice", age=26)
        results = backend.find_with_root_object(query2)  # 返回 []
        ```
        
        - 推荐使用字段路径查询：
        ```python
        # 按名字查询
        results = backend.find_with_values("name", "Alice")
        
        # 按年龄范围查询
        results = backend.find_with_values("age", [25, 26, 27])
        
        # 按地址城市查询
        results = backend.find_with_values("address.city", "Beijing")
        ```

    5. 标签语法：
        - 字段定义：必须声明为 List[str] 类型
        - 标签值要求：
            - 必须是非空字符串
            - 会自动去除首尾空白字符
            - 忽略空字符串和非字符串值
        - 查询语法：
            - 单标签：find_with_tags("tags", "python")
            - 多标签 OR：find_with_tags("tags", ["python", "web"])
            - 多标签 AND：find_with_tags("tags", ["python", "web"], match_all=True)

    6. 查询方法说明：
        常规索引查询：
        - find_with_values(field: str, values: Union[Any, List[Any]], match_all: bool = False) -> List[str]
            支持单值或多值查询：
            - 单值：find_with_values("age", 25)
            - 多值 OR：find_with_values("age", [25, 30])  # 匹配25或30
            - 多值 AND：find_with_values("age", [25, 30], match_all=True)  # 同时匹配25和30

        标签查询：
        - find_with_tags(field: str, tags: Union[str, List[str]], match_all: bool = False) -> List[str]
            支持单个或多个标签查询：
            - 单标签：find_with_tags("tags", "python")
            - 多标签 OR：find_with_tags("tags", ["python", "web"])  # 包含python或web
            - 多标签 AND：find_with_tags("tags", ["python", "web"], match_all=True)  # 同时包含python和web

        根对象查询：
            - find_with_root_object(model: BaseModel) -> List[str]
            使用完整的模型对象进行精确匹配

    7. 子类实现要求：
        (1) 必须实现的抽象方法：
        
        索引管理：
        - _add_to_index(field: str, value: Any, key: str) -> None
            将对象ID添加到指定字段和值的索引中
        
        - remove_from_index(field: str, value: Any, key: str) -> None
            从指定字段和值的索引中移除对象ID
        
        - rebuild_index(data: Dict[str, Any]) -> None
            重建整个索引，通常在数据恢复或迁移时使用
        
        - clear_index() -> None
            清空所有索引数据

        查询相关：
        - _find_with_single_value(field: str, value: Any) -> Set[str]
            用于基础值查询，返回匹配的对象ID集合
            - 用于支持 find_with_values 方法
            - 必须处理字段类型转换和验证
            - 返回结果无需排序
        
        - _find_with_single_tag(field: str, tag: str) -> Set[str]
            用于基础标签查询，返回匹配的对象ID集合
            - 用于支持 find_with_tags 方法
            - 必须验证标签字段类型
            - 返回结果无需排序
        
        - find_with_root_object(model: BaseModel) -> List[str]
            用于根对象查询，返回完全匹配的对象ID列表
            - 必须处理模型对象的序列化和比较
            - 返回的列表应当有序
        
        存储相关：
        - flush() -> None
            将内存中的索引变更持久化到存储
        
        - close() -> None
            关闭索引后端，确保数据已保存
        
        (2) 可选重写的方法：
        - prepare_query_value(field: str, value: Any) -> Tuple[Any, Optional[str]]
            自定义查询值处理，返回(处理后的值, 错误信息)
        
        - has_index(field: str) -> bool
            检查字段是否已建立索引
        
        - extract_and_convert_value(data: Any, field: str) -> Tuple[Any, Optional[str]]
            从数据中提取并转换索引值
        
        - get_stats() -> Dict[str, int]
            获取索引统计信息
        
        - clear_stats() -> None
            清除统计信息
        
        (3) 可选生命周期相关方法：
        - __init__(field_types: Dict[str, Any] = None, config: IndexConfig = None)
            初始化索引后端，设置字段类型和配置
        
        - __enter__() -> IndexBackend
            上下文管理器入口
        
        - __exit__(exc_type, exc_val, exc_tb) -> None
            上下文管理器出口，确保资源正确释放
    
    7. 统计支持：
        - updates: 索引更新次数
        - queries: 查询执行次数
        - cache_hits: 缓存命中次数
        - cache_misses: 缓存未命中次数
    """

    def __init__(
        self, 
        field_types: Dict[str, Any] = None,
        config: Optional[IndexConfig] = None,
        logger: Optional[logging.Logger] = None
    ):
        """初始化索引后端
        
        Args:
            field_types: 字段类型约束字典，键为字段路径，值为期望类型
                特殊路径 "." 表示对象本身的类型约束
            config: 索引配置对象
        """
        self.logger = logger or logging.getLogger(__name__)
        self._field_types = field_types or {}
        self._config = config or IndexConfig()
        self._stats = {
            "updates": 0,
            "queries": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "last_rebuild": None
        }
        
        # 验证字段路径格式
        if field_types:
            self.validate_field_paths()

        # 从环境变量读取标签数量限制
        self.MAX_TAGS = int(get_env('JIAOZI_INDEX_FIELD_MAX_TAGS'))

    # 标签管理接口
    def add_tags(self, field: str, tags: List[str], key: str) -> None:
        """添加标签"""
        if not self.has_index(field):
            raise KeyError(f"字段 {field} 未定义索引")
            
        field_type = self._field_types.get(field)
        self.logger.debug("Adding tags: field=%s, tags=%s, key=%s, field_type=%s", 
                       field, tags, key, field_type)
        
        if not (hasattr(field_type, '__origin__') and 
                field_type.__origin__ in (list, List) and 
                field_type.__args__[0] == str):
            raise TypeError(f"字段 {field} 不是标签类型")
            
        for tag in tags:
            if not isinstance(tag, str) or not tag.strip():
                self.logger.debug("Skipping invalid tag: %s", tag)
                continue
            cleaned_tag = tag.strip()
            self.logger.debug("Adding single tag: %s", cleaned_tag)
            self.add_to_index(field, cleaned_tag, key)

    def remove_tags(self, field: str, tags: List[str], key: str) -> None:
        """移除标签
        
        Args:
            field: 标签字段名
            tags: 标签列表
            key: 对象ID
            
        Raises:
            KeyError: 当字段未定义为标签索引时
            TypeError: 当字段类型不是 List[str] 时
        """
        if not self.has_index(field):
            raise KeyError(f"字段 {field} 未定义索引")
            
        field_type = self._field_types.get(field)
        if not (hasattr(field_type, '__origin__') and 
                field_type.__origin__ in (list, List) and 
                field_type.__args__[0] == str):
            raise TypeError(f"字段 {field} 不是标签类型")
            
        for tag in tags:
            if not isinstance(tag, str) or not tag.strip():
                continue
            # 从索引中移除标签
            self.remove_from_index(field, tag.strip(), key)

    def _validate_field_index(self, field: str) -> None:
        """验证字段是否已定义索引
        
        Args:
            field: 字段名
            
        Raises:
            KeyError: 字段未定义索引
        """
        if not self.has_index(field):
            raise KeyError(f"字段 {field} 未定义索引")

    def _validate_key(self, key: str) -> None:
        """验证文档ID"""
        if not key:
            raise ValueError("数据键不能为空")

    def _validate_field_value(self, field: str, value: Any) -> Any:
        """验证字段值"""
        self.logger.debug("Validating field value: field=%s, value=%s (type=%s)",
                       field, value, type(value))
        
        if value is None:
            raise ValueError(f"字段值不能为 None")
        
        expected_type = self._field_types[field]
        self.logger.debug("Expected type: %s", expected_type)
        
        # 处理标签字段（List[str]）
        if (hasattr(expected_type, '__origin__') and 
            expected_type.__origin__ in (list, List) and 
            expected_type.__args__[0] == str):
            # 标签字段：直接验证字符串类型
            if not isinstance(value, str):
                raise TypeError("添加的标签必须是字符串类型")
            return value.strip()
        
        # 处理布尔类型
        if expected_type == bool and isinstance(value, str):
            if value.lower() in ('true', 'yes', '1', 'on'):
                return True
            if value.lower() in ('false', '0', 'no', 'off'):
                return False
            raise TypeError("类型不匹配：无效的布尔值")
        
        # 处理 Decimal 类型
        if expected_type == Decimal:
            try:
                return Decimal(str(value))
            except (decimal.InvalidOperation, TypeError):
                raise TypeError(f"类型不匹配：无法将 {value} 转换为 Decimal 类型")
            
        # 处理 datetime 类型
        if expected_type == datetime:
            try:
                if isinstance(value, str):
                    # 尝试多种日期格式
                    for fmt in ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
                        try:
                            return datetime.strptime(value, fmt)
                        except ValueError:
                            continue
                raise ValueError
            except ValueError:
                raise TypeError(f"类型不匹配：无法将 {value} 转换为 datetime 类型")
        
        # 其他类型：尝试转换
        try:
            converted = expected_type(value)
            self.logger.debug("Converted value: %s (type=%s)", converted, type(converted))
            return converted
        except (ValueError, TypeError):
            raise TypeError(f"类型不匹配：无法将 {value} 转换为 {expected_type.__name__} 类型")

    def validate_field_paths(self) -> None:
        """验证字段路径格式的有效性"""
        for field_path in self._field_types:
            self._validate_field_path(field_path)

    def _validate_field_path(self, field_path: str) -> None:
        """验证字段路径格式"""
        if not field_path:
            raise ValueError("无效的字段路径格式: 字段名不能为空")
        
        # 检查路径长度限制
        if len(field_path.split('.')) > 5:  # 最大嵌套深度为5
            raise ValueError("无效的字段路径格式: 路径嵌套层级过深")
        
        # 检查起始和结尾字符
        if field_path.startswith('.'):
            raise ValueError("无效的字段路径格式: 路径不能以点号开始")
        if field_path.endswith('.'):
            raise ValueError("无效的字段路径格式: 路径不能以点号结束")
        if field_path.startswith('['):
            raise ValueError("无效的字段路径格式: 路径不能以数组索引开始")
            
        # 检查连续点号
        if '..' in field_path:
            raise ValueError("无效的字段路径格式: 连续的点号无效")
            
        # 检查数组索引格式
        parts = field_path.split('.')
        for part in parts:
            if '[' in part:
                # 检查基本格式
                if not part.endswith(']'):
                    raise ValueError("无效的字段路径格式: 未闭合的数组索引")
                    
                # 检查点号和数组索引的组合
                if part.startswith('.'):
                    raise ValueError("无效的字段路径格式: 数组索引前不能有点号")
                if part.endswith('.]'):
                    raise ValueError("无效的字段路径格式: 数组索引后不能直接跟点号")
                    
                # 解析和验证索引
                array_parts = part.split('[')
                field_name = array_parts[0]
                
                # 验证字段名
                if not field_name:
                    raise ValueError("无效的字段路径格式: 数组索引前必须有字段名")
                if not field_name.isidentifier():
                    raise ValueError("无效的字段路径格式: 字段名包含无效字符")
                    
                # 验证所有索引
                for array_part in array_parts[1:]:
                    if not array_part.endswith(']'):
                        raise ValueError("无效的字段路径格式: 未闭合的数组索引")
                        
                    index_str = array_part[:-1]
                    try:
                        index = int(index_str)
                        if index < 0:
                            raise ValueError("无效的字段路径格式: 数组索引不能为负数")
                        if index > 999999:  # 设置合理的上限
                            raise ValueError("无效的字段路径格式: 数组索引超出范围")
                        if index_str.startswith('0') and len(index_str) > 1:
                            raise ValueError("无效的字段路径格式: 数组索引不能有前导零")
                    except ValueError as e:
                        if "invalid literal for int()" in str(e):
                            raise ValueError("无效的字段路径格式: 数组索引必须是数字")
                        raise
            else:
                # 验证普通字段名
                if not part.isidentifier():
                    raise ValueError("无效的字段路径格式: 字段名包含无效字符")
                if part[0].isdigit():
                    raise ValueError("无效的字段路径格式: 字段名不能以数字开始")
                if ' ' in part:
                    raise ValueError("无效的字段路径格式: 字段名不能包含空格")
                if not all(c.isalnum() or c == '_' for c in part):
                    raise ValueError("无效的字段路径格式: 字段名只能包含字母、数字和下划线")

    def _parse_field_path(self, path: str) -> List[Union[str, int]]:
        """解析字段路径为访问序列
        
        Args:
            path: 字段路径字符串
            
        Returns:
            List[Union[str, int]]: 字段访问序列
            
        Examples:
            >>> _parse_field_path("user.profile.name")
            ['user', 'profile', 'name']
            >>> _parse_field_path("tags[0]")
            ['tags', 0]
            >>> _parse_field_path("items[0].name")
            ['items', 0, 'name']
        """
        if not path:
            return []
            
        parts = []
        current = ""
        
        i = 0
        while i < len(path):
            char = path[i]
            if char == '.':
                if current:
                    parts.append(current)
                    current = ""
            elif char == '[':
                if current:
                    parts.append(current)
                    current = ""
                # 解析数组索引
                i += 1
                index = ""
                while i < len(path) and path[i] != ']':
                    index += path[i]
                    i += 1
                if not index.isdigit():
                    raise ValueError(f"无效的数组索引: {index}")
                parts.append(int(index))
            else:
                current += char
            i += 1
            
        if current:
            parts.append(current)
            
        return parts

    def extract_and_convert_value(self, data: Any, field_path: str) -> Tuple[Any, List[str]]:
        """提取并转换字段值"""
        if data is None:
            return None, []
        
        # 处理根对象查询
        if field_path == ".":
            return data, ["."]
        
        # 解析路径，支持数组索引
        parts = []
        current = data
        
        # 分割路径，处理数组索引
        for part in field_path.split('.'):
            # 处理数组索引 [n]
            if '[' in part and ']' in part:
                base = part[:part.index('[')]
                if base:
                    parts.append(base)
                    
                # 提取所有索引
                indices = re.findall(r'\[(\d+)\]', part)
                if not indices:
                    return None, parts
                    
                # 逐个应用索引
                try:
                    if base:
                        if isinstance(current, dict):
                            current = current[base]
                        elif isinstance(current, BaseModel):
                            current = getattr(current, base)
                        else:
                            return None, parts
                            
                    for idx in indices:
                        idx = int(idx)
                        parts.append(f"[{idx}]")
                        if not isinstance(current, (list, tuple)) or idx >= len(current):
                            return None, parts
                        current = current[idx]
                except (IndexError, KeyError, AttributeError, ValueError):
                    return None, parts
            else:
                parts.append(part)
                try:
                    if isinstance(current, dict):
                        if part not in current:
                            return None, parts
                        current = current[part]
                    elif isinstance(current, BaseModel):
                        current = getattr(current, part)
                    elif hasattr(current, part):
                        current = getattr(current, part)
                    else:
                        return None, parts
                except (KeyError, AttributeError):
                    return None, parts
                
        # 处理可索引对象
        if isinstance(current, Indexable):
            return current.to_index_key(), parts
        
        # 处理标签列表
        field_type = self._field_types.get(field_path)
        if field_type and hasattr(field_type, '__origin__') and field_type.__origin__ in (list, List):
            if not isinstance(current, (list, tuple)) or not current:
                return None, parts
                
            # 验证标签列表的元素类型
            element_type = field_type.__args__[0]
            if not all(isinstance(tag, element_type) for tag in current):
                return None, parts
                
            # 过滤和清理标签
            tags = []
            for tag in current[:self.MAX_TAGS]:  # 限制标签数量
                if isinstance(tag, str):
                    tag = tag.strip()
                    if tag:
                        tags.append(tag)
                else:
                    tags.append(tag)
            return tags if tags else None, parts
        
        # 拒绝未实现 Indexable 的复杂类型
        if isinstance(current, (dict, list)) and not isinstance(current, Indexable):
            return None, parts
        
        # 确保返回的值与字段类型匹配
        if field_type and not isinstance(current, field_type):
            try:
                current = field_type(current)
            except (ValueError, TypeError):
                self.logger.warning(
                    "字段类型转换失败: path=%s, value=%s, expected_type=%s",
                    field_path, current, field_type.__name__
                )
                return None, parts
        
        return current, parts

    def convert_to_index_key(self, value: Any, field_path: str = None) -> Optional[str]:
        """将值转换为索引键
        
        Args:
            value: 要转换的值
            field_path: 字段路径
            
        Returns:
            Optional[str]: 索引键，如果无法转换则返回 None
        """
        if value is None:
            return None
            
        # 处理可索引对象
        if isinstance(value, Indexable):
            return value.to_index_key()
            
        # 处理 Pydantic 模型
        if isinstance(value, BaseModel):
            return str(hash(value.model_dump_json()))
            
        # 处理基本类型
        try:
            return str(value)
        except Exception as e:
            self.logger.error("无法转换为索引键: %s", e)
            return None

    def is_field_type_valid(self, field_path: str, value: Any) -> bool:
        """验证字段值是否符合类型约束
        
        Args:
            field_path: 字段路径
            value: 字段值
            
        Returns:
            bool: 是否符合类型约束
        """
        if field_path not in self._field_types:
            return False
            
        expected_type = self._field_types[field_path]
        
        # 处理标签列表
        if (hasattr(expected_type, '__origin__') and 
            expected_type.__origin__ in (list, List)):
            if not isinstance(value, (list, tuple)):
                return False
            element_type = expected_type.__args__[0]
            return all(isinstance(item, element_type) for item in value)
            
        # 处理可索引对象
        if isinstance(value, Indexable):
            return True
            
        # 处理 Pydantic 模型
        if isinstance(expected_type, type) and issubclass(expected_type, BaseModel):
            return isinstance(value, expected_type)
            
        # 处理基本类型
        return isinstance(value, expected_type)

    def extract_value_from_path(self, data: Any, path_parts: List[Union[str, int]]) -> Any:
        """从复杂结构中提取值
        
        Args:
            data: 数据对象
            path_parts: 路径部分列表
            
        Returns:
            Any: 提取的值
        """
        value = data
        for part in path_parts:
            if isinstance(value, BaseModel):
                try:
                    value = getattr(value, str(part))
                except AttributeError:
                    return None
            elif isinstance(value, dict):
                try:
                    value = value[part]
                except KeyError:
                    return None
            elif isinstance(value, (list, tuple)) and isinstance(part, int):
                try:
                    value = value[part]
                except IndexError:
                    return None
            elif hasattr(value, part):
                value = getattr(value, part)
            else:
                return None
        return value

    def find_with_root_object(self, model: BaseModel) -> List[str]:
        """根对象查询实现
        
        Args:
            model: Pydantic模型对象
            
        Returns:
            List[str]: 匹配的对象ID列表
        """
        pass
    def add_to_index(self, field: str, value: Any, key: str) -> None:
        """添加索引值，支持单值或值列表
        
        Args:
            field: 字段名
            value: 单个值或值列表
            key: 数据键
        """
        # 检查字段索引是否存在
        self._validate_field_index(field)
        self._validate_key(key)
        self.logger.debug("Adding to index: field=%s, value=%s (type=%s), key=%s", 
                       field, value, type(value), key)
        
        # 统一转换为列表处理
        value_list = value if isinstance(value, (list, set)) else [value]
        
        # 处理每个值
        for single_value in value_list:
            # 转换并验证值
            converted_value = self._validate_field_value(field, single_value)
            self.logger.debug("Processing value: %s -> %s", single_value, converted_value)
            if converted_value is not None:
                self._add_to_index(field, converted_value, key)

    @abstractmethod
    def _add_to_index(self, field_path: str, value: Any, key: str) -> None:
        """添加单个索引项
        
        Args:
            field_path: 字段名
            value: 索引值
            key: 数据键
            
        Raises:
            ValueError: 当字段类型不匹配时
            RuntimeError: 当添加失败时
        """
        pass

    def has_index(self, field_path: str) -> bool:
        """检查字段是否已建立索引
        
        Args:
            field_path: 字段名
            
        Returns:
            bool: 是否存在索引
        """
        pass

    def get_index_size(self) -> int:
        """获取索引大小"""
        pass

    def get_index_memory_usage(self) -> int:
        """获取索引内存使用量（字节）"""
        pass

    def get_field_index_size(self, field_path: str) -> int:
        """获取指定字段的索引大小
        
        Args:
            field_path: 字段名
            
        Returns:
            int: 该字段的索引项数量
        """
        pass

    def save_indexes(self) -> None:
        """保存索引到持久化存储
        
        Raises:
            RuntimeError: 当保存失败时
        """
        pass
        
    def load_indexes(self) -> None:
        """从持久化存储加载索引
        
        Raises:
            RuntimeError: 当加载失败时
        """
        pass
        
    def clear_indexes(self) -> None:
        """清空所有索引
        
        Raises:
            RuntimeError: 当操作失败时
        """
        pass

    def rebuild_indexes(self) -> None:
        """重建所有索引
        
        Raises:
            RuntimeError: 当重建失败时
        """
        pass

    def update_index(self, data: Any, key: str) -> None:
        """更新索引
        
        Args:
            data: 要索引的数据对象
            key: 数据键
            
        Raises:
            ValueError: 当数据不符合类型约束时
            RuntimeError: 当索引更新失败时
        """
        pass

    def remove_from_index(self, key: str) -> None:
        """删除指定数据项的所有索引
        
        Args:
            key: 数据键
            
        Raises:
            RuntimeError: 当删除失败时
        """
        pass

    def prepare_query_value(self, field_path: str, query_value: Any) -> Tuple[Optional[Any], Optional[str]]:
        """准备查询值"""
        self.logger.debug("prepare_query_value called with: field=%s, value=%s (type=%s)", 
                       field_path, query_value, type(query_value))
        
        if field_path not in self._field_types:
            self.logger.warning("字段 %s 未定义类型约束", field_path)
            return query_value, None
            
        target_type = self._field_types[field_path]
        self.logger.debug("Target type: %s", target_type)
        
        # 处理标签字段
        if hasattr(target_type, '__origin__') and target_type.__origin__ in (list, List):
            element_type = target_type.__args__[0]
            if element_type is str:
                if query_value is None:
                    return None, "标签查询值不能为空"
                if not isinstance(query_value, str):
                    return None, "标签查询值必须是字符串"
                if not query_value.strip():
                    return None, "标签查询值不能为空字符串"
                return query_value.strip(), None
        
        # 处理其他类型的空值
        if query_value is None:
            return None, None
            
        # 处理标签字段
        if hasattr(target_type, '__origin__') and target_type.__origin__ in (list, List):
            element_type = target_type.__args__[0]
            if element_type is str:
                if isinstance(query_value, str) and query_value.strip():
                    return query_value.strip(), None
                if not isinstance(query_value, str):
                    return None, "标签查询值必须是字符串"
                return None, "标签查询值不能为空"
        
        # 如果值已经是目标类型
        if isinstance(query_value, target_type):
            if hasattr(query_value, 'to_index_key'):
                return query_value.to_index_key(), None
            return query_value, None
        
        # 尝试转换为目标类型
        try:
            if isinstance(query_value, str):
                # 布尔值转换
                if target_type is bool:
                    if query_value.lower() in ('true', '1', 'yes', 'on'):
                        return True, None
                    if query_value.lower() in ('false', '0', 'no', 'off'):
                        return False, None
                    return None, "无效的布尔值"
                    
                # 日期时间转换
                elif target_type is datetime:
                    for fmt in [
                        "%Y-%m-%d %H:%M:%S",
                        "%Y-%m-%d",
                        "%Y/%m/%d",
                        "%Y%m%d%H%M%S",
                        "%Y%m%d"
                    ]:
                        try:
                            return datetime.strptime(query_value, fmt), None
                        except ValueError:
                            continue
                    return None, f"不支持的日期时间格式: {query_value}"
                    
            # 其他类型转换
            converted = target_type(query_value)
            if hasattr(converted, 'to_index_key'):
                return converted.to_index_key(), None
            return converted, None
            
        except Exception as e:
            return None, f"类型转换失败: {str(e)}"

    def _make_index_key(self, field_path: str, value: Any) -> str:
        """生成索引键
        
        Args:
            field_path: 字段名
            value: 字段值
            
        Returns:
            str: 索引键，格式为 "idx:{field_path}:{value}"
        """
        return f"idx:{field_path}:{value}"
        
    def _parse_index_key(self, key: str) -> Tuple[str, str]:
        """解析索引键
        
        Args:
            key: 索引键
            
        Returns:
            Tuple[str, str]: (field_path, value)
        """
        _, field_path, value = key.split(":", 2)
        return field_path, value

    def _make_field_key(self, field_path: str) -> str:
        """生成字段元数据键
        
        Args:
            field_path: 字段名
            
        Returns:
            str: 字段键，格式为 "field_path:{field_path}"
        """
        return f"field_path:{field_path}"

    def prepare_for_storage(self, data: Any) -> Any:
        """准备数据用于存储
        
        将复杂对象转换为可序列化的格式。处理顺序：
        1. None 值直接返回
        2. Pydantic 模型使用 model_dump()
        3. 数据类使用 asdict()
        4. 具有 to_dict() 方法的对象调用该方法
        5. 具有 __dict__ 属性的对象转换为字典
        6. 列表和字典递归处理其元素
        7. 其他类型直接返回
        
        Args:
            data: 要转换的数据
            
        Returns:
            转换后的可序列化数据
            
        Examples:
            >>> backend = SomeIndexBackend()
            >>> user = User(name="Alice", age=25)
            >>> serializable = backend.prepare_for_storage(user)
            >>> storage.set("user1", serializable)
        """
        if data is None:
            return None
            
        # Pydantic 模型
        if isinstance(data, BaseModel):
            return data.model_dump()
            
        # 数据类
        if hasattr(data, '__dataclass_fields__'):
            from dataclasses import asdict
            return asdict(data)
            
        # 自定义序列化方法
        if hasattr(data, 'to_dict'):
            return data.to_dict()
            
        # 普通对象
        if hasattr(data, '__dict__'):
            return data.__dict__
            
        # 递归处理容器类型
        if isinstance(data, list):
            return [self.prepare_for_storage(item) for item in data]
        if isinstance(data, dict):
            return {
                str(k): self.prepare_for_storage(v) 
                for k, v in data.items()
            }
            
        # 其他类型直接返回
        return data

    @abstractmethod
    def _find_with_single_value(self, field: str, value: Any) -> Set[str]:
        """单值查询实现（内部方法）"""
        pass

    @abstractmethod
    def _find_with_single_tag(self, field: str, tag: str) -> Set[str]:
        """单个标签查询实现（内部方法）"""
        pass
    def find_with_tags(self, field: str, tags: Union[str, List[str]], match_all: bool = False) -> List[str]:
        """使用标签查询
        
        Args:
            field: 标签字段名
            tags: 标签或标签列表
            match_all: 是否要求匹配所有标签
            
        Returns:
            匹配的文档ID列表
        """
        # 增加查询统计
        if self._config.enable_stats:
            self._stats["queries"] += 1

        # 验证字段类型
        field_type = self._field_types.get(field)
        if not (hasattr(field_type, '__origin__') and 
                field_type.__origin__ in (list, List) and 
                field_type.__args__[0] == str):
            raise TypeError("查询的标签必须是字符串类型")
        
        # 标准化标签列表
        if isinstance(tags, str):
            tag_list = [tags]
        else:
            tag_list = tags
        
        # 过滤并验证标签
        valid_tags = []
        for tag in tag_list:
            if tag is None or not isinstance(tag, str):
                continue
            tag = tag.strip()
            if tag:  # 忽略空字符串
                valid_tags.append(tag)
        
        if not valid_tags:  # 如果没有有效标签，返回空列表
            return []
        
        # 执行标签查询
        final_result = set()
        for tag in valid_tags:
            result = self._find_with_single_tag(field, tag)
            if not final_result:
                final_result = result
            elif match_all:
                final_result &= result  # AND 操作
            else:
                final_result |= result  # OR 操作
        
        return sorted(final_result)

    def find_with_values(self, field: str, values: Union[Any, List[Any]], match_all: bool = False) -> List[str]:
        """多值查询实现
        
        Args:
            field: 字段名
            values: 单个值或值列表
            match_all: 是否要求匹配所有值
                - True: 返回同时匹配所有值的对象（AND）
                - False: 返回匹配任意值的对象（OR）
                
        Returns:
            List[str]: 匹配的对象ID列表
            
        Raises:
            KeyError: 当字段未定义索引时
            TypeError: 当字段值类型不匹配时
        """
        self._validate_field_index(field)
        self._update_stats("queries")
        
        if not self.has_index(field):
            raise KeyError(f"字段 {field} 未定义索引")
            
        # 统一转换为列表处理
        value_list = values if isinstance(values, list) else [values]
        self.logger.debug("查询值列表: %s", value_list)
        
        # 不捕获 TypeError，让它向上传播
        results = []
        for value in value_list:
            converted_value = self._validate_field_value(field, value)
            if converted_value is None:
                continue
                
            prepared_value, error = self.prepare_query_value(field, converted_value)
            if error:
                raise TypeError(error)
                
            if prepared_value is None:
                continue
                
            keys = self._find_with_single_value(field, prepared_value)
            if keys:
                results.append(keys)
        
        if not results:
            return []
            
        # 根据匹配模式合并结果
        final_result = set.intersection(*results) if match_all else set.union(*results)
        return sorted(final_result)

