from typing import Dict, Any, List, Callable, Optional, Union, Tuple, Protocol, runtime_checkable, Type, Set
from abc import ABC, abstractmethod
import logging
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel
from collections.abc import Sequence
from collections import defaultdict
import re

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

class IndexBackend(ABC):
    """索引后端基类
    
    本类实现了对各种数据类型的索引支持，遵循以下设计原则：
    
    1. 索引目标支持：
       - 简单对象（str, int, float, bool 等基本类型）
       - 字典、列表、元组等复杂结构（仅用于路径访问）
       - Pydantic 模型
       - 实现了 Indexable 协议的自定义对象
       
    2. 索引值要求：
       - 仅接受简单类型的属性值作为索引
       - 特例1：实现了 Indexable 协议的对象可以自定义索引键生成
       - 特例2：类型一致的列表可以作为标签集合使用
       
    3. 路径语法：
       - 使用点号（.）分隔的路径表示属性访问
       - 使用方括号 [n] 表示列表索引访问
       - 单个点号（.）表示对象本身
       
    子类实现要求：
    
    1. 必须实现的核心方法：
       - add_to_index: 添加单个索引项
       - remove_from_index: 删除指定所有者的所有索引
       - find_with_tag: 标签查询
       - find_with_value: 值查询
       - find_with_root_object: 根对象查询
       
    2. 可选实现的方法：
       - save_indexes: 持久化存储（如果需要）
       - load_indexes: 加载持久化数据（如果需要）
       - clear_indexes: 清空索引（如果支持）
       - rebuild_indexes: 重建索引（如果支持）
       
    3. 性能统计方法：
       - get_index_size: 获取索引大小
       - get_index_memory_usage: 获取内存使用量
       
    4. 辅助方法（基类已实现）：
       - convert_to_index_key: 转换索引键
       - is_field_type_valid: 类型检查
       - extract_value_from_path: 路径访问
       
    注意事项：
    1. 子类可以根据自身特点选择合适的存储结构
    2. 不要求子类必须支持所有索引目标类型
    3. 可以根据实际需求简化或扩展路径语法
    4. 持久化方案由子类自行决定
    """

    # 添加类变量定义最大嵌套深度
    MAX_NESTING_DEPTH = 5

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
        self._validate_field_paths()

        # 从环境变量读取标签数量限制
        self.MAX_TAGS = int(get_env('JIAOZI_INDEX_FIELD_MAX_TAGS'))

    def _validate_field_paths(self) -> None:
        """验证字段路径格式的有效性"""
        for field_path in self._field_types:
            try:
                # 测试路径解析
                self._validate_field_path(field_path)
            except ValueError as e:
                self.logger.error(f"无效的字段路径格式: {field_path}")
                raise ValueError(f"无效的字段路径格式 '{field_path}': {str(e)}")

    def _validate_field_path(self, field_path: str) -> None:
        """验证字段路径格式"""
        if not field_path:
            raise ValueError("字段路径不能为空")
            
        # 检查无效字符
        if field_path.startswith('[') or field_path.endswith('['):
            raise ValueError(f"字段路径 '{field_path}' 格式无效：不能以 [ 开头或结尾")
            
        # 检查括号匹配
        if field_path.count('[') != field_path.count(']'):
            raise ValueError(f"字段路径 '{field_path}' 中的方括号不匹配")
            
        # 检查数组索引格式
        parts = field_path.split('.')
        for part in parts:
            if '[' in part:
                # 检查方括号内是否为数字
                array_parts = part.split('[')
                if not array_parts[0]:  # 防止 [0]field_path 这样的格式
                    raise ValueError(f"字段路径 '{field_path}' 格式无效：数组索引前必须有字段名")
                for array_part in array_parts[1:]:
                    if not array_part.endswith(']'):
                        raise ValueError(f"字段路径 '{field_path}' 中的数组索引格式无效")
                    try:
                        int(array_part[:-1])
                    except ValueError:
                        raise ValueError(f"字段路径 '{field_path}' 中的数组索引必须是整数")
                    
        # 检查连续点号
        if '..' in field_path:
            raise ValueError(f"字段路径 '{field_path}' 包含连续的点号")

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

    def find_with_index(self, field_path: str, value: Any) -> List[str]:
        """使用索引查找匹配的对象
        
        支持两种查询模式：
        1. 标签查询：当字段类型为标签列表时，查找包含指定标签的对象
        2. 值匹配：直接比较字段值与查询值
        
        Args:
            field_path: 字段路径
            value: 查询值
            
        Returns:
            List[str]: 匹配对象的 ID 列表
            
        Raises:
            ValueError: 当查询值类型不匹配时
        """
        self._update_stats("queries")
        
        try:
            # 处理标签查询
            field_type = self._field_types.get(field_path)
            if field_type and hasattr(field_type, '__origin__') and field_type.__origin__ in (list, List):
                element_type = field_type.__args__[0]
                if isinstance(value, element_type):
                    return self.find_with_tag(field_path, value)
            
            # 处理根对象查询
            if field_path == "." and isinstance(value, BaseModel):
                return self.find_with_root_object(value)
                
            # 处理常规查询
            return self.find_with_value(field_path, value)
            
        except Exception as e:
            self.logger.error("查询执行失败: field_path=%s, value=%s, error=%s", 
                          field_path, value, str(e))
            return []

    def get_stats(self) -> Dict[str, Any]:
        """获取索引统计信息
        
        Returns:
            Dict[str, Any]: 包含各项统计数据的字典
        """
        return self._stats.copy()

    def clear_stats(self) -> None:
        """清除统计信息"""
        self._stats.update({
            "updates": 0,
            "queries": 0,
            "cache_hits": 0,
            "cache_misses": 0
        })

    def _update_stats(self, stat_name: str) -> None:
        """更新统计信息"""
        if self._config.enable_stats:
            self._stats[stat_name] = self._stats.get(stat_name, 0) + 1
            self.logger.debug("更新统计信息: %s=%d", stat_name, self._stats[stat_name])

    def prepare_query_value(self, field_path: str, query_value: Any) -> Tuple[Optional[Any], Optional[str]]:
        """准备查询值，确保类型匹配
        
        特殊处理：
        - 标签字段：只接受非空字符串作为查询值
        - 可索引对象：调用其 to_index_key() 方法
        - 基本类型：支持字符串到目标类型的转换
        """
        if field_path not in self._field_types:
            self.logger.warning(f"字段 {field_path} 未定义类型约束")
            return query_value, None
            
        target_type = self._field_types[field_path]
        
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

    # -------- 必须实现的核心方法 --------
    @abstractmethod
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

    @abstractmethod 
    def remove_from_index(self, key: str) -> None:
        """删除指定所有者的所有索引
        
        Args:
            key: 数据键
            
        Raises:
            RuntimeError: 当删除失败时
        """
        pass

    @abstractmethod
    def find_with_tag(self, field_path: str, tag: str) -> List[str]:
        """标签查询实现
        
        Args:
            field_path: 标签字段名
            tag: 标签值
            
        Returns:
            List[str]: 包含指定标签的对象ID列表
        """
        pass

    @abstractmethod
    def find_with_value(self, field_path: str, value: Any) -> List[str]:
        """常规值查询实现
        
        Args:
            field_path: 字段名
            value: 查询值
            
        Returns:
            List[str]: 匹配的对象ID列表
        """
        pass

    @abstractmethod
    def find_with_root_object(self, model: BaseModel) -> List[str]:
        """根对象查询实现
        
        Args:
            model: Pydantic模型对象
            
        Returns:
            List[str]: 匹配的对象ID列表
        """
        pass

    @abstractmethod
    def add_to_index(self, field_path: str, value: Any, key: str) -> None:
        """添加单个索引项
        
        Args:
            field_path: 字段名
            value: 索引值
            key: 所有者ID
            
        Raises:
            ValueError: 当字段类型不匹配时
            RuntimeError: 当添加失败时
        """
        pass

    @abstractmethod
    def has_index(self, field_path: str) -> bool:
        """检查字段是否已建立索引
        
        Args:
            field_path: 字段名
            
        Returns:
            bool: 是否存在索引
        """
        pass

    @abstractmethod
    def get_index_size(self) -> int:
        """获取索引大小"""
        pass

    @abstractmethod
    def get_index_memory_usage(self) -> int:
        """获取索引内存使用量（字节）"""
        pass

    @abstractmethod
    def get_field_index_size(self, field_path: str) -> int:
        """获取指定字段的索引大小
        
        Args:
            field_path: 字段名
            
        Returns:
            int: 该字段的索引项数量
        """
        pass

    # -------- 可选实现的方法 --------
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
