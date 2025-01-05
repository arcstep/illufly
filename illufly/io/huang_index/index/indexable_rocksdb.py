from typing import Type, Optional, Iterator, Tuple, Any
from pydantic import BaseModel
from ..base_rocksdb import BaseRocksDB
from .index_manager import IndexManager

class IndexableRocksDB(BaseRocksDB):
    def __init__(self, db_path: str):
        super().__init__(db_path)
        self.index_manager = IndexManager(self)
    
    def register_model_index(self, model_class: Type[BaseModel], field_path: str, index_type: str = "exact"):
        """注册模型索引"""
        self.index_manager.register_model_index(model_class, field_path, index_type)
    
    def set(self, collection: str, key: str, value: BaseModel):
        """设置对象时自动更新索引"""
        try:
            old_value = self.get(collection, key)
        except ValueError:  # 处理键格式非法的情况
            old_value = None
        except Exception:  # 处理其他可能的错误
            old_value = None
        
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
        
    def iter_keys(
        self,
        collection: str,
        prefix: Optional[str] = None,
        field_path: Optional[str] = None,
        field_value: Optional[Any] = None,
        limit: Optional[int] = None,
        reverse: bool = False
    ) -> Iterator[str]:
        """扩展的键迭代方法，支持索引查询
        
        Args:
            collection: 集合名称
            prefix: 键前缀（与索引查询互斥）
            field_path: 索引字段路径
            field_value: 索引字段值
            limit: 限制返回数量
            reverse: 是否反向迭代
        """
        if field_path is not None and field_value is not None:
            # 使用索引查询
            yield from self.index_manager.query_by_index(
                collection, field_path, field_value, limit, reverse
            )
        else:
            # 使用普通前缀查询
            yield from super().iter_keys(
                collection, prefix, limit=limit, reverse=reverse
            )
    
    def all(self, collection: str, prefix: Optional[str] = None,
            field_path: Optional[str] = None, field_value: Optional[Any] = None,
            limit: Optional[int] = None, reverse: bool = False) -> Iterator[Tuple[str, Any]]:
        """扩展的查询方法，支持索引查询"""
        for key in self.iter_keys(collection, prefix, field_path, field_value, limit, reverse):
            value = self.get(collection, key)
            if value is not None:
                yield key, value
    
    def first(self, collection: str, prefix: Optional[str] = None,
             field_path: Optional[str] = None, field_value: Optional[Any] = None) -> Optional[Tuple[str, Any]]:
        """获取第一个匹配的记录"""
        for item in self.all(collection, prefix, field_path, field_value, limit=1):
            return item
        return None
    
    def last(self, collection: str, prefix: Optional[str] = None,
            field_path: Optional[str] = None, field_value: Optional[Any] = None) -> Optional[Tuple[str, Any]]:
        """获取最后一个匹配的记录"""
        for item in self.all(collection, prefix, field_path, field_value, limit=1, reverse=True):
            return item
        return None

