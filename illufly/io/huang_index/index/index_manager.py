from typing import Type, Any, Optional, Dict
from pydantic import BaseModel
from ..base_rocksdb import BaseRocksDB

class IndexManager:
    INDEX_CF = "indexes"      # 正向索引列族
    REVERSE_CF = "reverse"    # 反向索引列族
    
    def __init__(self, db: BaseRocksDB):
        self.db = db
        self._model_indexes = {}  # 缓存模型的索引配置
        
        # 确保索引列族存在
        self.db.set_collection_options(self.INDEX_CF, {})
        self.db.set_collection_options(self.REVERSE_CF, {})
        
    def register_model_index(self, model_class: Type[BaseModel], field_path: str, index_type: str = "exact"):
        """注册模型的索引配置"""
        if model_class not in self._model_indexes:
            self._model_indexes[model_class] = {}
        self._model_indexes[model_class][field_path] = index_type

    def update_indexes(self, collection: str, key: str, old_value: Optional[BaseModel], new_value: BaseModel):
        """更新索引"""
        model_class = type(new_value)
        if model_class not in self._model_indexes:
            return
            
        # 获取旧的索引记录
        reverse_key = f"rev:{key}:idx"
        old_indexes = self.db.get(self.REVERSE_CF, reverse_key) or {"fields": {}}
        
        # 准备新的索引记录
        new_indexes = {"fields": {}}
        
        # 使用基类的批量写入
        with self.db.batch_write() as batch:
            # 1. 删除旧索引
            for field_path, old_value in old_indexes["fields"].items():
                if field_path in self._model_indexes[model_class]:
                    old_index_key = self._make_index_key(collection, field_path, old_value, key)
                    batch.delete(self.INDEX_CF, old_index_key)
            
            # 2. 创建新索引
            for field_path in self._model_indexes[model_class]:
                new_value = self._get_field_value(new_value, field_path)
                if new_value is not None:
                    # 保存正向索引
                    index_key = self._make_index_key(collection, field_path, new_value, key)
                    batch.set(self.INDEX_CF, index_key, None)
                    
                    # 记录到新的反向索引
                    new_indexes["fields"][field_path] = new_value
            
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