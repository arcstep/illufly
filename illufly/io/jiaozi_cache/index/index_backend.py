from typing import Dict, Any, List, Optional, Callable, Type, Union
from abc import ABC, abstractmethod
import logging
import time

from .config import IndexConfig

class IndexBackend(ABC):
    """索引后端基类
    
    该类提供了索引实现的基础框架，包括：
    1. 类型验证和约束检查
    2. 数据路径解析和值提取
    3. 索引键生成策略
    4. 性能统计和监控
    
    子类需要实现以下抽象方法：
    - update_index: 更新或创建索引
    - find_with_index: 使用索引查找数据
    - rebuild_indexes: 重建所有索引
    
    Attributes:
        _config (IndexConfig): 索引配置
        _field_types (Dict): 字段类型约束映射
        _path_cache (Dict): 字段路径解析缓存
        _stats (Dict): 性能统计数据
    """

    def __init__(
        self, 
        field_types: Dict[str, Any] = None,
        config: Optional[IndexConfig] = None,
        logger: Optional[logging.Logger] = None
    ):
        """初始化索引后端
        
        Args:
            field_types: 字段类型约束
            config: 索引配置
            logger: 日志记录器
        """
        self.logger = logger or logging.getLogger(self.__name__)
        self.logger.info("初始化索引后端")
        
        self._field_types = field_types or {}
        self._config = config or IndexConfig()
        self._field_types = {}
        self._path_cache: Dict[str, List[str]] = {}
        self._stats = {
            "updates": 0,
            "queries": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "last_rebuild": None
        }
        
        if field_types:
            self.logger.debug("开始验证字段类型约束")
            if not isinstance(field_types, dict):
                self.logger.error("field_types 必须是字典类型")
                raise ValueError("field_types 必须是字典类型")
            
            for key, type_spec in field_types.items():
                if not isinstance(key, str):
                    self.logger.error("字段名必须是字符串类型: %s", key)
                    raise ValueError("字段名必须是字符串类型")
                if not (isinstance(type_spec, type) or 
                       isinstance(type_spec, list) or 
                       type_spec is Any or
                       hasattr(type_spec, 'to_index_key')):
                    self.logger.error("字段 %s 的类型规范无效", key)
                    raise ValueError(f"字段 {key} 的类型规范无效")
                
                if isinstance(type_spec, list):
                    if not all(isinstance(t, type) for t in type_spec):
                        self.logger.error("字段 %s 的类型列表包含无效类型", key)
                        raise ValueError(f"字段 {key} 的类型列表包含无效类型")
            
            self._field_types = field_types
            self.logger.debug("字段类型约束验证完成: %s", self._field_types)

    def is_field_type_valid(self, field: str, value: Any) -> bool:
        """验证字段值是否符合类型约束
        
        支持以下类型验证：
        1. 单一类型（如 str, int）
        2. 类型列表（如 [str, int]）
        3. Any类型（接受任何值）
        4. Indexable协议（具有to_index_key方法）
        
        Args:
            field: 字段名
            value: 要验证的值
            
        Returns:
            bool: 值是否符合类型约束
        """
        self.logger.debug("验证字段类型: field=%s, value=%s", field, value)
        if field not in self._field_types:
            return True
            
        type_spec = self._field_types[field]
        
        # 如果类型是Any，始终返回True
        if type_spec is Any:
            return True
            
        # 如果是类型列表，检查值是否匹配其中任一类型
        if isinstance(type_spec, list):
            valid = any(isinstance(value, t) for t in type_spec)
            if not valid:
                self.logger.warning("字段值不符合类型列表约束: field=%s, value=%s, types=%s", 
                                  field, value, type_spec)
            return valid
            
        # 单一类型的情况
        valid = isinstance(value, type_spec)
        if not valid:
            self.logger.warning("字段值不符合类型约束: field=%s, value=%s, type=%s",
                              field, value, type_spec)
        return valid

    def _get_value_by_path(self, data: Any, field: str) -> Optional[Any]:
        """从数据对象中提取指定路径的值
        
        支持以下数据访问方式：
        1. 字典键访问（data["key"]）
        2. 属性访问（data.key）
        3. 列表索引访问（data[0]）
        4. 嵌套路径访问（data.key1.key2[0].key3）
        
        Args:
            data: 数据对象
            field: 字段路径（如 "metadata.tags[0]"）
            
        Returns:
            Optional[Any]: 提取的值，如果路径无效则返回None
        """
        self.logger.debug("提取字段值: field=%s", field)
        # 使用缓存的路径分割
        if field not in self._path_cache:
            self._path_cache[field] = field.split('.')
        parts = self._path_cache[field]
        
        try:
            current = data
            for part in parts:
                if isinstance(current, dict):
                    current = current[part]
                elif isinstance(current, (list, tuple)):
                    current = current[int(part)]
                elif hasattr(current, part):
                    current = getattr(current, part)
                else:
                    self.logger.debug("字段路径无效: field=%s, part=%s", field, part)
                    return None
                
            result = list(current) if isinstance(current, (list, tuple, set)) else current
            self.logger.debug("字段值提取成功: field=%s, value=%s", field, result)
            return result
        except (KeyError, IndexError, AttributeError, ValueError) as e:
            self.logger.debug("字段值提取失败: field=%s, error=%s", field, str(e))
            return None

    def convert_to_index_key(self, value: Any, field: str = None) -> str:
        """将值转换为索引键字符串
        
        转换策略：
        1. None -> 空字符串
        2. Indexable对象 -> 调用to_index_key()
        3. 可哈希对象 -> 哈希值字符串
        4. 字典 -> 键值对拼接
        5. 列表/元组 -> 元素拼接
        6. 其他 -> 字符串表示
        
        Args:
            value: 要转换的值
            field: 字段名（可选，用于上下文相关的转换）
            
        Returns:
            str: 生成的索引键
        """
        self.logger.debug("转换索引键: value=%s, field=%s", value, field)
        if value is None:
            return ""
            
        # 支持自定义索引键生成
        if hasattr(value, "to_index_key"):
            key = value.to_index_key()
            self.logger.debug("使用自定义索引键生成: key=%s", key)
            return key
            
        # 使用缓存的哈希值
        if hasattr(value, "__hash__") and value.__hash__ is not None:
            key = str(hash(value))
            self.logger.debug("使用哈希值作为索引键: key=%s", key)
            return key
            
        if isinstance(value, dict):
            key = ".".join(f"{k}.{self.convert_to_index_key(v)}" 
                          for k, v in sorted(value.items()))
            self.logger.debug("字典转换为索引键: key=%s", key)
            return key
            
        if isinstance(value, (list, tuple)):
            key = ".".join(self.convert_to_index_key(item) for item in value)
            self.logger.debug("列表/元组转换为索引键: key=%s", key)
            return key
            
        key = str(value)
        self.logger.debug("转换为字符串索引键: key=%s", key)
        return key

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
        """使用索引查找数据
        
        Args:
            field: 索引字段
            value: 查找值
            
        Returns:
            List[str]: 匹配的所有者ID列表
            
        Raises:
            KeyError: 当指定字段没有建立索引时
        """
        self._update_stats("queries")
        pass
    
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
