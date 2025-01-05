from typing import Type, Any, Optional, Dict, Iterator
from pydantic import BaseModel
from ..base_rocksdb import BaseRocksDB
from .accessor import AccessorRegistry
from .path_parser import PathParser

class IndexManager:
    INDEX_CF = "indexes"      # 正向索引列族
    REVERSE_CF = "reverse"    # 反向索引列族
    
    def __init__(self, db: BaseRocksDB):
        self.db = db
        self._model_indexes = {}  # 缓存模型的索引配置
        self._accessor_registry = AccessorRegistry()
        self._path_parser = PathParser()
        
        # 确保索引列族存在
        self.db.set_collection_options(self.INDEX_CF, {})
        self.db.set_collection_options(self.REVERSE_CF, {})
        
    def register_model_index(self, model_class: Type[BaseModel], field_path: str, index_type: str = "exact"):
        """注册模型的索引配置"""
        if model_class not in self._model_indexes:
            self._model_indexes[model_class] = {}
        self._model_indexes[model_class][field_path] = index_type

    def update_indexes(self, collection: str, key: str, old_value: Any, new_value: Any):
        """更新索引
        
        Args:
            collection: 集合名称
            key: 记录键
            old_value: 旧值（可能为None）
            new_value: 新值（可能为None）
        """
        # 处理删除操作
        if new_value is None:
            if old_value is None:
                return  # 没有任何操作需要执行
            value_type = type(old_value)
        else:
            value_type = type(new_value)
        
        # 检查是否需要索引处理
        if value_type not in self._model_indexes:
            return
            
        # 获取值访问器
        accessor = self._accessor_registry.get_accessor(old_value or new_value)
        
        # 获取旧的索引记录（安全获取）
        reverse_key = f"rev:{key}:idx"
        try:
            old_indexes = self.db.get(self.REVERSE_CF, reverse_key) or {"fields": {}}
        except Exception:
            old_indexes = {"fields": {}}
        
        # 准备新的索引记录
        new_indexes = {"fields": {}}
        
        with self.db.batch_write() as batch:
            # 1. 删除旧索引（如果存在）
            if old_indexes["fields"]:
                for field_path, old_value in old_indexes["fields"].items():
                    if field_path in self._model_indexes[value_type]:
                        old_index_key = self._make_index_key(collection, field_path, old_value, key)
                        batch.delete(self.INDEX_CF, old_index_key)
            
            # 2. 创建新索引（如果有新值）
            if new_value is not None:
                for field_path in self._model_indexes[value_type]:
                    # 使用访问器获取字段值
                    path_segments = self._path_parser.parse(field_path)
                    field_value = accessor.get_field_value(new_value, path_segments)
                    
                    if field_value is not None:
                        # 保存正向索引
                        index_key = self._make_index_key(collection, field_path, field_value, key)
                        batch.set(self.INDEX_CF, index_key, None)
                        
                        # 记录到新的反向索引
                        new_indexes["fields"][field_path] = field_value
            
            # 3. 更新反向索引
            if new_indexes["fields"]:
                batch.set(self.REVERSE_CF, reverse_key, new_indexes)
            else:
                batch.delete(self.REVERSE_CF, reverse_key)

    def _make_index_key(self, collection: str, field_path: str, field_value: Any, target_key: str) -> str:
        """构造索引键"""
        # 根据字段类型格式化值
        if isinstance(field_value, (int, float)):
            formatted_value = f"{field_value:0>10}"  # 数值固定长度
        elif isinstance(field_value, datetime):
            formatted_value = field_value.strftime("%Y%m%d%H%M%S")
        else:
            formatted_value = str(field_value)
        
        return f"idx:{collection}:{field_path}:{formatted_value}:k:{target_key}"

    def _get_field_value(self, model: BaseModel, field_path: str) -> Any:
        """获取模型的嵌套字段值"""
        value = model
        for part in field_path.split('.'):
            if hasattr(value, part):
                value = getattr(value, part)
            else:
                return None
        return value 

    def query_by_index(
        self,
        collection: str,
        field_path: str,
        value: Any, 
        limit: Optional[int] = None,
        reverse: bool = False
    ) -> Iterator[str]:
        """通过索引查询键
        
        Args:
            collection: 集合名称
            field_path: 索引字段路径
            value: 查询值
            limit: 限制返回数量
            reverse: 是否反向查询
            
        Returns:
            Iterator[str]: 匹配的键迭代器
        """
        index_key_prefix = self._make_index_key(collection, field_path, value, "")
        
        # 使用基类的迭代方法
        for key in self.db.iter_keys(
            self.INDEX_CF,
            prefix=index_key_prefix,
            limit=limit,
            reverse=reverse
        ):
            # 从索引键中提取目标键
            target_key = key.split(":k:")[-1]
            yield target_key 