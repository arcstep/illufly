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
        self.default_collection = ModelRegistry.DEFAULT_CF
        
        # 确保元数据列族存在
        if "__MODELS_META__" not in self.list_collections():
            self.set_collection_options("__MODELS_META__", self._default_cf_options)

        if self.default_collection not in self.list_collections():
            self.set_collection_options(self.default_collection, self._default_cf_options)

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
                try:
                    return self._create_dynamic_model(model_id, model_data, model_class)
                except Exception as e:
                    logger.error(f"模型 {model_id} 数据验证失败: {e}")
                    raise

            return obj
            
        self._db.set_dumps(dumps)
        self._db.set_loads(loads)
    
    def _create_dynamic_model(self, 
                            model_id: str, 
                            data: Dict[str, Any],
                            model_class: Optional[Type[BaseModel]] = None) -> BaseModel:
        """根据数据动态创建模型实例
        
        Args:
            model_id: 模型ID
            data: 模型数据
            model_class: 可选的模型类，如果提供则使用此类构造实例
            
        Returns:
            BaseModel: 模型实例
        """
        if model_class is not None:
            # 如果提供了模型类，直接使用它来构造实例
            return model_class.model_validate(data)
        
        # 否则使用动态模型
        if model_id in self._dynamic_models:
            dynamic_model = self._dynamic_models[model_id]
        else:
            # 从数据推断字段类型
            fields = {
                key: (type(value), ...) for key, value in data.items()
            }
            
            # 创建动态模型类
            dynamic_model = create_model(
                model_id,
                __base__=DynamicModel,
                **fields
            )
            self._dynamic_models[model_id] = dynamic_model
        
        # 使用动态模型创建实例
        return dynamic_model(**data)  # 注意这里直接使用构造函数而不是 model_validate

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

        collection = collection or self.default_collection
        return ModelRegistry.register_model(
            model_class=model_class,
            model_id=model_id,
            key_pattern=key_pattern,
            collection=collection,
            db=self,
            allow_update=allow_update
        )
    
    def get_model_meta(self,
                        model_id: Optional[str] = None,
                        model_class: Optional[Type[BaseModel]] = None,
                        collection: Optional[str] = None) -> Optional[Dict]:
        """获取模型元数据"""

        collection = collection or self.default_collection
        return ModelRegistry.get_model(
            model_id=model_id,
            model_class=model_class,
            collection=collection,
            db=self
        )
    
    def list_models_meta(self) -> Dict[str, Dict]:
        """列出所有模型元数据"""

        return ModelRegistry.list_models(db=self)
    
    def update_model_meta(self,
                updates: Dict[str, Any],
                model_id: Optional[str] = None,
                model_class: Optional[Type[BaseModel]] = None,
                collection: Optional[str] = None) -> bool:
        """更新模型元数据"""

        collection = collection or self.default_collection
        return ModelRegistry.update_model(
            updates=updates,
            model_class=model_class,
            model_id=model_id,
            collection=collection,
            db=self
        )

    # === 模型实例 CRUD ===
    def create_model(self,
                    instance: BaseModel,
                    model_id: Optional[str] = None,
                    collection: Optional[str] = None,
                    **kwargs) -> str:
        """创建模型实例（新增）
        
        Args:
            instance: 模型实例
            model_id: 可选的模型ID，默认使用实例的类名
            collection: 可选的集合名称
            
        Returns:
            生成的键
        """

        collection = collection or self.default_collection
        metadata = self.get_model_meta(
            model_id=model_id or instance.__class__.__name__,
            collection=collection
        )
        if not metadata:
            raise ValueError("模型未注册")
            
        # 自动从实例中获取键所需的参数
        key = ModelRegistry.gen_key(
            instance=instance,
            model_id=model_id,
            collection=collection,
            db=self,
            **kwargs
        )
        
        super().set(metadata['collection'], key, instance)
        return key
    
    def read_model(
        self,
        key: str,
        collection: Optional[str] = None,
        model_class: Optional[Type[BaseModel]] = None
    ) -> Optional[BaseModel]:
        """读取模型实例（查询）
        
        Args:
            key: 已知的键
            collection: 可选的集合名称
            model_class: 可选的模型类，用于构造完整实例
        """

        collection = collection or self.default_collection
        data = super().get(collection, key)
        if data is None:
            return None
            
        return self._create_dynamic_model(
            model_id=model_id,
            data=data.model_dump(),
            model_class=model_class
        )
    
    def update_model(self,
                    key: str,
                    instance: BaseModel,
                    collection: Optional[str] = None) -> None:
        """更新模型实例（修改）
        
        Args:
            key: 已知的键
            instance: 更新后的模型实例
            collection: 可选的集合名称
        """

        collection = collection or self.default_collection
        return super().set(collection, key, instance)
    
    def delete_model(self,
                    key: str,
                    collection: Optional[str] = None) -> None:
        """删除模型实例
        
        Args:
            key: 已知的键
            collection: 可选的集合名称
        """

        collection = collection or self.default_collection
        return super().delete(collection, key)
    
    
    def all_models(self,
                   model_id: str,
                   collection: Optional[str] = None,
                   id: Optional[str] = None,
                   prefix: Optional[str] = None,
                   infix: Optional[str] = None,
                   suffix: Optional[str] = None,
                   start: Optional[str] = None,
                   end: Optional[str] = None,
                   limit: Optional[int] = None) -> Iterator[Tuple[str, BaseModel]]:
        """列举模型实例
        
        Args:
            model_id: 模型ID
            collection: 可选的集合名称
            id: 可选的实例ID
            prefix: 可选的键前缀
            infix: 可选的键中缀
            suffix: 可选的键后缀
            start: 可选的开始键
            end: 可选的结束键
            limit: 可选的限制数量
        """

        collection = collection or self.default_collection
        parts_key = ":".join([part for part in [model_id, prefix, id, infix, suffix] if part])
        return super().all(
            collection=collection,
            prefix=parts_key,
            start=start,
            end=end,
            limit=limit
        )
