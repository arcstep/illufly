from typing import Optional, Any, Dict, Type
import msgpack
from datetime import datetime
from pydantic import BaseModel
from pydantic.json_schema import JsonSchemaMode
from pydantic_core import CoreSchema, core_schema

from .rocksdb import RocksDB
from .patterns import KeyPattern
from .model import ModelRegistry

import logging
import importlib

logger = logging.getLogger(__name__)

class ModelRocksDB(RocksDB):
    """支持 Pydantic 模型管理的 RocksDB"""
    
    def __init__(self, *args, **kwargs):
        """初始化带模型管理的 RocksDB"""
        super().__init__(*args, **kwargs)
        self._model_classes = {}  # 用于缓存模型类
        
        # 确保元数据列族存在
        if "__MODELS_META__" not in self.list_collections():
            self.set_collection_options("__MODELS_META__", self._default_cf_options)
            
        # 设置 Pydantic 模型序列化方法
        def dumps(obj: Any) -> bytes:
            if isinstance(obj, BaseModel):
                return msgpack.packb({
                    "__model__": obj.__class__.__name__,
                    "__collection__": getattr(obj, '__collection__', None),
                    "data": obj.model_dump(mode='json')
                })
            if isinstance(obj, datetime):
                return msgpack.packb(obj.isoformat())
            return msgpack.packb(obj)
            
        def loads(data: bytes) -> Any:
            """反序列化数据"""
            obj = msgpack.unpackb(data)
            if isinstance(obj, dict) and "__model__" in obj:
                model_id = obj["__model__"]
                model_class = self._get_model_class(model_id)
                if model_class is None:
                    logger.error(f"找不到模型类: {model_id}")
                    raise ValueError(f"找不到模型类: {model_id}")
                try:
                    return model_class.model_validate(obj["data"])
                except Exception as e:
                    logger.error(f"反序列化失败: {e}")
                    raise
            return obj
            
        self._db.set_dumps(dumps)
        self._db.set_loads(loads)
    
    def _get_model_class(self, model_id: str) -> Optional[Type[BaseModel]]:
        """获取模型类"""
        return self._model_classes.get(model_id)
    
    def register_model(self, 
                      model_class: Type[BaseModel], 
                      model_id: Optional[str] = None,
                      **kwargs) -> bool:
        """注册模型"""
        model_id = model_id or model_class.__name__
        # 缓存模型类
        self._model_classes[model_id] = model_class
        return ModelRegistry.register_model(
            model_class=model_class,
            model_id=model_id,
            db=self,
            **kwargs
        )
    
    def get_model(self,
                 instance: Optional[BaseModel] = None,
                 model_id: Optional[str] = None,
                 collection: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """获取模型元数据"""
        return ModelRegistry.get_model(
            instance=instance,
            model_id=model_id,
            collection=collection,
            db=self
        )
    
    def list_models(self, collection: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """列出所有模型元数据"""
        return ModelRegistry.list_models(
            collection=collection,
            db=self
        )
    
    def make_key(self,
                 instance: BaseModel,
                 model_id: Optional[str] = None,
                 collection: Optional[str] = None,
                 **kwargs) -> str:
        """为模型实例生成键"""
        return ModelRegistry.get_key(
            instance=instance,
            model_id=model_id,
            collection=collection,
            db=self,
            **kwargs
        )
    
    def save(self,
            instance: BaseModel,
            model_id: Optional[str] = None,
            collection: Optional[str] = None,
            **key_kwargs) -> str:
        """保存模型实例"""
        # 先获取模型元数据
        metadata = ModelRegistry.get_model(
            instance=instance,
            model_id=model_id,
            db=self  # 不传 collection，让它自动查找
        )
        if not metadata:
            raise ValueError("模型未注册")
        
        # 使用元数据中的集合或指定的集合
        collection = collection or metadata['collection']
        
        # 生成键
        key = self.make_key(
            instance=instance,
            model_id=model_id,
            collection=collection,  # 使用正确的集合
            **key_kwargs
        )
            
        self.set(metadata['collection'], key, instance)
        return key
    
    def load(self,
            key: str,
            model_id: str,
            collection: Optional[str] = None) -> Optional[BaseModel]:
        """加载模型实例"""
        metadata = self.get_model(model_id=model_id, collection=collection)
        if not metadata:
            raise ValueError("模型未注册")
            
        return self.get(metadata['collection'], key)