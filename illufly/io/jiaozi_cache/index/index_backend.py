from typing import Dict, Any, List, Callable, Optional, Union, Tuple, Protocol, runtime_checkable, Type, Set
from abc import ABC, abstractmethod
import logging
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel
from collections.abc import Sequence
from collections import defaultdict

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
       
    4. 类型约束：
       - 通过 field_types 字典定义每个字段的类型
       - 支持嵌套结构的类型检查
       - 对标签列表进行元素类型一致性检查
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
                if not array_parts[0]:  # 防止 [0]field 这样的格式
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

    def extract_and_convert_value(self, data: Any, field_path: str) -> Tuple[Optional[Any], List[Union[str, int]]]:
        """从数据对象中提取并转换字段值"""
        if field_path == ".":
            return data, ["."]
            
        path_parts = self._parse_field_path(field_path)
        
        if len(path_parts) > self.MAX_NESTING_DEPTH:
            self.logger.error("访问路径 {} 超过最大深度 {}".format(field_path, self.MAX_NESTING_DEPTH))
            return None, path_parts
        
        try:
            value = data
            for part in path_parts:
                if isinstance(value, BaseModel):
                    try:
                        value = getattr(value, str(part))
                    except AttributeError:
                        self.logger.debug(f"Pydantic模型中不存在字段: {part}")
                        return None, path_parts
                elif isinstance(value, dict):
                    try:
                        value = value[part]
                    except KeyError:
                        self.logger.debug(f"字典中不存在键: {part}")
                        return None, path_parts
                elif isinstance(value, (list, tuple)) and isinstance(part, int):
                    try:
                        value = value[part]
                    except IndexError:
                        self.logger.debug(f"列表索引越界: {part}")
                        return None, path_parts
                elif hasattr(value, part):
                    value = getattr(value, part)
                else:
                    self.logger.debug(f"无法访问路径: {field_path}, 当前部分: {part}")
                    return None, path_parts

            # 首先检查是否是标签列表字段
            field_type = self._field_types.get(field_path)
            
            self.logger.info("正在处理字段 {}: 值类型 = {}, 字段类型 = {}".format(
                field_path, type(value).__name__, field_type
            ))
            
            # 标签列表处理
            if field_type and hasattr(field_type, '__origin__'):
                self.logger.info("字段 {} 的类型信息: origin = {}, args = {}".format(
                    field_path, 
                    field_type.__origin__,
                    getattr(field_type, '__args__', None)
                ))
                
                if (field_type.__origin__ in (list, List) and 
                    len(field_type.__args__) == 1 and 
                    field_type.__args__[0] is str and
                    isinstance(value, (list, tuple))):
                    
                    # 检查所有元素是否都是字符串
                    if not all(isinstance(tag, str) for tag in value):
                        self.logger.warning("标签列表包含非字符串元素")
                        return None, path_parts
                        
                    # 过滤并限制标签数量
                    valid_tags = [tag.strip() for tag in value if tag.strip()]
                    if not valid_tags:
                        self.logger.warning("标签列表中没有有效的标签")
                        return None, path_parts
                        
                    if len(valid_tags) > self.MAX_TAGS:
                        self.logger.warning(
                            "标签数量超过限制：当前 {} 个，限制 {} 个，将截取前 {} 个标签".format(
                                len(valid_tags), self.MAX_TAGS, self.MAX_TAGS
                            )
                        )
                        valid_tags = valid_tags[:self.MAX_TAGS]
                        
                    self.logger.info("成功处理标签列表，返回 {} 个有效标签".format(len(valid_tags)))
                    return valid_tags, path_parts
                    
            # 验证其他类型
            if not self.is_field_type_valid(field_path, value):
                self.logger.warning("字段值类型不匹配：{} = {}".format(field_path, value))
                return None, path_parts
                
            # 处理可索引对象
            if hasattr(value, 'to_index_key'):
                return value.to_index_key(), path_parts
            
            # 检查最终值是否为复杂类型
            if isinstance(value, (dict, list, tuple)):
                self.logger.error("不支持的复杂类型：{}，需要实现 Indexable 协议".format(
                    type(value).__name__
                ))
                return None, path_parts
            
            return value, path_parts
            
        except Exception as e:
            self.logger.error("值提取失败：{} - {}".format(field_path, str(e)))
            return None, path_parts

    def convert_to_index_key(self, value: Any, field_path: str = None) -> Optional[str]:
        """将值转换为索引键"""
        if value is None:
            return None
        
        # 处理可索引对象
        if hasattr(value, 'to_index_key'):
            return value.to_index_key()
        
        # 处理 Pydantic 模型
        if isinstance(value, BaseModel):
            return str(hash(value.model_dump_json()))
        
        # 处理基本类型
        if isinstance(value, (str, int, float, bool)):
            return str(value)
        
        # 对于其他复杂类型，拒绝处理
        if isinstance(value, (dict, list, tuple)):
            self.logger.error(
                f"不支持的复杂类型作为索引值： {type(value).__name__}，"
                f"请实现 Indexable 协议以自定义索引键生成"
            )
            return None
        
        return str(value)

    def is_field_type_valid(self, field_path: str, value: Any) -> bool:
        """验证字段值类型是否匹配"""
        field_type = self._field_types.get(field_path)
        if not field_type:
            return True
        
        # 处理标签列表类型
        if hasattr(field_type, '__origin__') and field_type.__origin__ in (list, List):
            if not isinstance(value, (list, tuple)):
                return False
            # 对于标签列表，我们只需要验证它是列表类型
            # 具体的元素验证在 extract_and_convert_value 中处理
            return True
        
        return isinstance(value, field_type)

    @abstractmethod
    def update_index(self, data: Any, owner_id: str) -> None:
        """更新索引
        
        Args:
            data: 要索引的数据对象
            owner_id: 数据所有者ID
            
        Raises:
            ValueError: 当数据不符合类型约束时
            IndexError: 当索引更新失败时
        """
        pass

    @abstractmethod 
    def remove_from_index(self, owner_id: str) -> None:
        pass

    @abstractmethod
    def find_with_index(self, field: str, value: Any) -> List[str]:
        """使用索引查找匹配的对象
        
        支持两种查询模式：
        1. 标签查询：当字段类型为标签列表时，查找包含指定标签的对象
        2. 值匹配：直接比较字段值与查询值
        
        Args:
            field: 字段路径
            value: 查询值
            
        Returns:
            List[str]: 匹配对象的 ID 列表
        """
        self._update_stats("queries")
        result = set()
        
        # 处理标签列表查询
        field_type = self._field_types.get(field)
        if field_type and hasattr(field_type, '__origin__') and field_type.__origin__ in (list, List):
            element_type = field_type.__args__[0]
            if isinstance(value, element_type):
                for owner_id, data in self._data.items():
                    tags, _ = self.extract_and_convert_value(data, field)
                    if tags and value in tags:
                        result.add(owner_id)
                return list(result)
        
        # 常规查询
        query_value, error = self.prepare_query_value(field, value)
        if error:
            self.logger.warning(f"查询值验证失败: {error}")
            return []
            
        # 如果是根对象查询，使用 model_dump_json 进行比较
        if field == "." and isinstance(query_value, BaseModel):
            query_json = query_value.model_dump_json()
            for owner_id, data in self._data.items():
                if isinstance(data, BaseModel) and data.model_dump_json() == query_json:
                    result.add(owner_id)
            return list(result)
            
        for owner_id, data in self._data.items():
            indexed_value, _ = self.extract_and_convert_value(data, field)
            if indexed_value == query_value:
                result.add(owner_id)
            
        return list(result)
    
    @abstractmethod
    def has_index(self, field: str) -> bool:
        pass
    
    @abstractmethod
    def rebuild_indexes(self, data_iterator: Callable[[], List[tuple[str, Any]]]) -> None:
        """重建所有索引
        
        Args:
            data_iterator: 返回(owner_id, data)元组列表的迭代器
            
        Raises:
            RuntimeError: 当重建过程失败时
        """
        self.logger.info("开始重建索引")
        self._stats["last_rebuild"] = time.time()
        pass

    def get_stats(self) -> Dict[str, Any]:
        """获取索引统计信息"""
        self.logger.debug("获取统计信息: %s", self._stats)
        return self._stats.copy()

    def clear_stats(self) -> None:
        """清除统计信息"""
        self.logger.info("清除统计信息")
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

    @abstractmethod
    def get_index_size(self) -> int:
        """获取索引大小"""
        pass

    @abstractmethod
    def get_index_memory_usage(self) -> int:
        """获取索引内存使用量（字节）"""
        pass

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
