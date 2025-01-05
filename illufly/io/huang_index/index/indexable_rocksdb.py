from typing import Type, Optional
from pydantic import BaseModel
from ..base_rocksdb import BaseRocksDB
from .index_manager import IndexManager

class IndexableRocksDB(BaseRocksDB):
    def __init__(self, db_path: str):
        super().__init__(db_path)
        self.index_manager = IndexManager(self)
    
    def set(self, collection: str, key: str, value: BaseModel):
        """设置对象时自动更新索引"""
        # 获取旧值
        old_value = self.get(collection, key)
        
        # 保存新值
        super().set(collection, key, value)
        
        # 更新索引
        self.index_manager.update_indexes(collection, key, old_value, value)
        
    def delete(self, collection: str, key: str):
        """删除对象时自动清理索引"""
        # 获取旧值
        old_value = self.get(collection, key)
        
        if old_value:
            # 清理索引
            self.index_manager.update_indexes(collection, key, old_value, None)
        
        # 删除原始值
        super().delete(collection, key)
        
    def register_model_index(self, model_class: Type[BaseModel], field_path: str, index_type: str = "exact"):
        """注册模型索引"""
        self.index_manager.register_model_index(model_class, field_path, index_type)

