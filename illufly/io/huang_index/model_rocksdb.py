from typing import Optional, Any, Dict, Type, Iterator, Tuple
import msgpack
from datetime import datetime
from pydantic import BaseModel, ConfigDict, create_model
from pydantic.json_schema import JsonSchemaMode
from pydantic_core import CoreSchema, core_schema

from .rocksdb import RocksDB
from .patterns import KeyPattern
from .model import ModelRegistry

import logging
import importlib

logger = logging.getLogger(__name__)

class DynamicModel(BaseModel):
    """动态模型基类，提供友好的属性访问"""
    model_config = ConfigDict(extra='allow')  # 允许额外字段

    def __getattr__(self, name: str) -> Any:
        """提供更友好的属性访问"""
        try:
            return self.__dict__[name]
        except KeyError:
            raise AttributeError(f"'{self.__class__.__name__}' 没有属性 '{name}'")

class ModelRocksDB(RocksDB):
    """支持 Pydantic 模型管理的 RocksDB"""
    
    def __init__(self, *args, models: Dict[str, Type[BaseModel]] = None, **kwargs):
        """初始化带模型管理的 RocksDB"""
        super().__init__(*args, **kwargs)
        self._model_classes = models or {}  # 用于缓存模型类
        self._dynamic_models = {}  # 缓存动态生成的模型类
        
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
                model_data = obj["data"]
                
                # 1. 首先尝试获取已注册的实际模型类
                model_class = self._get_model_class(model_id)
                
                # 2. 如果找不到已注册的类，创建或获取动态模型类
                if model_class is None:
                    model_class = self._create_dynamic_model(model_id, model_data)
                    logger.debug(f"使用动态模型类 {model_id} 加载数据")
                
                try:
                    return model_class.model_validate(model_data)
                except Exception as e:
                    logger.error(f"模型 {model_id} 数据验证失败: {e}")
                    raise
            return obj
            
        self._db.set_dumps(dumps)
        self._db.set_loads(loads)
    
    def _create_dynamic_model(self, model_id: str, data: Dict[str, Any]) -> Type[BaseModel]:
        """根据数据动态创建模型类"""
        if model_id in self._dynamic_models:
            return self._dynamic_models[model_id]

        # 从数据推断字段类型
        fields = {
            key: (type(value), ...) for key, value in data.items()
        }
        
        # 创建动态模型
        model = create_model(
            model_id,
            __base__=DynamicModel,  # 使用我们的基类
            **fields
        )
        
        self._dynamic_models[model_id] = model
        return model

    def _get_model_class(self, model_id: str) -> Optional[Type[BaseModel]]:
        """获取模型类，优先从缓存获取"""
        # 先从已注册的模型类缓存中查找
        if model_id in self._model_classes:
            return self._model_classes[model_id]
            
        # 尝试从元数据中获取并加载类
        try:
            metadata = ModelRegistry.get_model(model_id=model_id, db=self)
            if metadata and 'model_class' in metadata:
                module_path, class_name = metadata['model_class'].rsplit('.', 1)
                module = importlib.import_module(module_path)
                model_class = getattr(module, class_name)
                self._model_classes[model_id] = model_class
                return model_class
        except Exception as e:
            logger.debug(f"无法加载模型类 {model_id}: {e}")
            
        return None

    def register_model(
        self,
        model_class: Type[BaseModel],
        model_id: Optional[str] = None,
        key_pattern: Optional[KeyPattern] = None,
        collection: Optional[str] = None,
        allow_update: bool = False
    ) -> bool:
        """注册模型元数据"""
        return ModelRegistry.register_model(
            model_class=model_class,
            model_id=model_id,
            key_pattern=key_pattern,
            collection=collection,
            db=self,
            allow_update=allow_update
        )
    
    def get_model_meta(self, model_id: str = None, model_class: Type[BaseModel] = None, collection: Optional[str] = None) -> Optional[Dict]:
        """获取模型元数据"""
        return ModelRegistry.get_model(model_id=model_id, model_class=model_class, collection=collection, db=self)
    
    def list_models_meta(self, collection: Optional[str] = None) -> Dict[str, Dict]:
        """列出所有模型元数据"""
        return ModelRegistry.list_models(collection=collection, db=self)
    
    def update_model_meta(self,
                 updates: Dict[str, Any],
                 model_id: Optional[str] = None,
                 model_class: Optional[Type[BaseModel]] = None,
                 collection: Optional[str] = None) -> bool:
        """更新模型元数据"""
        return ModelRegistry.update_model(
            updates=updates,
            model_class=model_class,
            model_id=model_id,
            collection=collection,
            db=self
        )
    
    def get_model(self,
                 model_id: str,
                 collection: Optional[str] = None,
                 id: str = None,
                 infix: Optional[str] = None,
                 suffix: Optional[str] = None) -> Optional[BaseModel]:
        """获取模型实例，即使没有原始类定义也能工作"""
        metadata = self.get_model_meta(model_id, collection)
        if not metadata:
            raise ValueError("模型未注册")
            
        key = ModelRegistry.get_key(
            model_id=model_id,
            collection=collection,
            db=self,
            id=id,
            infix=infix,
            suffix=suffix
        )
        
        return super().get(metadata['collection'], key)
    
    # === 模型实例 CRUD ===
    def create_model(self,
                    instance: BaseModel,
                    model_id: Optional[str] = None,
                    collection: Optional[str] = None) -> str:
        """创建模型实例（新增）
        
        Args:
            instance: 模型实例
            model_id: 可选的模型ID，默认使用实例的类名
            collection: 可选的集合名称
            
        Returns:
            生成的键
        """
        metadata = self.get_model_meta(
            model_id or instance.__class__.__name__,
            collection
        )
        if not metadata:
            raise ValueError("模型未注册")
            
        # 自动从实例中获取键所需的参数
        key = ModelRegistry.get_key(
            instance=instance,
            model_id=model_id,
            collection=collection,
            db=self
        )
        
        super().set(metadata['collection'], key, instance)
        return key
    
    def read_model(self,
                   key: str,
                   model_id: str,
                   collection: Optional[str] = None,
                   model_class: Optional[Type[BaseModel]] = None) -> Optional[BaseModel]:
        """读取模型实例（查询）
        
        Args:
            key: 已知的键
            model_id: 模型ID
            collection: 可选的集合名称
            model_class: 可选的模型类，用于构造完整实例
        """
        metadata = self.get_model_meta(model_id, collection)
        if not metadata:
            raise ValueError("模型未注册")
            
        data = super().get(metadata['collection'], key)
        if data is None:
            return None
            
        if model_class is not None:
            return model_class.model_validate(data.model_dump())
        return data
    
    def update_model(self,
                    key: str,
                    instance: BaseModel,
                    model_id: Optional[str] = None,
                    collection: Optional[str] = None) -> None:
        """更新模型实例（修改）
        
        Args:
            key: 已知的键
            instance: 更新后的模型实例
            model_id: 可选的模型ID
            collection: 可选的集合名称
        """
        metadata = self.get_model_meta(
            model_id or instance.__class__.__name__,
            collection
        )
        if not metadata:
            raise ValueError("模型未注册")
            
        # 验证键是否存在
        if not self.exists(metadata['collection'], key):
            raise ValueError(f"找不到键: {key}")
            
        super().set(metadata['collection'], key, instance)
    
    def delete_model(self,
                    key: str,
                    model_id: str,
                    collection: Optional[str] = None) -> None:
        """删除模型实例
        
        Args:
            key: 已知的键
            model_id: 模型ID
            collection: 可选的集合名称
        """
        metadata = self.get_model_meta(model_id, collection)
        if not metadata:
            raise ValueError("模型未注册")
            
        super().delete(metadata['collection'], key)
    
    def list_models(self,
                   model_id: str,
                   collection: Optional[str] = None,
                   prefix: Optional[str] = None,
                   model_class: Optional[Type[BaseModel]] = None) -> Iterator[Tuple[str, BaseModel]]:
        """列举模型实例
        
        Args:
            model_id: 模型ID
            collection: 可选的集合名称
            prefix: 可选的键前缀
            model_class: 可选的模型类
        """
        metadata = self.get_model_meta(model_id, collection)
        if not metadata:
            raise ValueError("模型未注册")
            
        # 如果没有提供前缀，使用模型ID作为前缀
        prefix = prefix or f"{model_id}:"
        
        for key, value in self.scan_items(metadata['collection'], prefix=prefix):
            if model_class is not None:
                value = model_class.model_validate(value.model_dump())
            yield key, value
    
    def find_model_by_id(self,
                        id: str,
                        model_id: str,
                        collection: Optional[str] = None,
                        model_class: Optional[Type[BaseModel]] = None) -> Optional[BaseModel]:
        """通过ID查找模型实例
        
        Args:
            id: 实例ID
            model_id: 模型ID
            collection: 可选的集合名称
            model_class: 可选的模型类
        """
        metadata = self.get_model_meta(model_id, collection)
        if not metadata:
            raise ValueError("模型未注册")
            
        # 构造一个临时实例用于生成键
        temp_instance = BaseModel()
        temp_instance.id = id
        
        key = ModelRegistry.get_key(
            instance=temp_instance,
            model_id=model_id,
            collection=collection,
            db=self
        )
        
        return self.read_model(key, model_id, collection, model_class)