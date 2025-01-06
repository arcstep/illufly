from typing import Optional, Dict, Any, Type, List, Union
from pydantic import BaseModel, Field, ConfigDict, field_serializer
from pydantic.fields import PydanticUndefined
from datetime import datetime
import uuid
import json
import logging

from .patterns import KeyPattern

logger = logging.getLogger(__name__)

class ModelMetadata(BaseModel):
    """模型元数据（系统表）"""
    model_id: str  # 模型ID（唯一标识）
    collection: str  # 集合名称
    key_pattern: KeyPattern  # 键模式
    fields: Dict[str, Dict[str, Any]]  # 字段定义
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    @field_serializer('created_at', 'updated_at')
    def serialize_datetime(self, dt: datetime):
        return dt.isoformat()
    
    @field_serializer('key_pattern')
    def serialize_key_pattern(self, key_pattern: KeyPattern):
        return key_pattern.value  # 序列化为枚举值
    
    model_config = ConfigDict(
        arbitrary_types_allowed=True
    )

class HuangIndexModel(BaseModel):
    """黄索引基础模型（可选继承）"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    infix: Optional[str] = None
    suffix: Optional[str] = Field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )
    
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra='allow'
    )

class ModelRegistry:
    """模型注册表"""
    DEFAULT_CF = "default"  # 默认列族
    MODELS_META_CF = "__MODELS_META__"  # 元数据专用列族
    MODEL_KEY_PREFIX = "models"  # 元数据键前缀
    
    @staticmethod
    def _resolve_model_id(
        model_class: Optional[Type[BaseModel]] = None, 
        model_id: Optional[str] = None
    ) -> str:
        """解析模型ID"""
        if model_id:
            return model_id
        if model_class:
            return model_class.__name__
        raise ValueError("必须提供 model_class 或 model_id 其中之一")

    @classmethod
    def get_model_key(cls, model_id: str, collection: str=None) -> str:
        """获取模型键"""
        model_id = model_id or ""
        collection = collection or cls.DEFAULT_CF
        return f"{cls.MODEL_KEY_PREFIX}:{collection}:{model_id}"

    @classmethod
    def register_model(
        cls, 
        model_class: Type[BaseModel],
        model_id: Optional[str] = None,
        key_pattern: Optional[KeyPattern] = None,
        collection: Optional[str] = None,
        db: Optional['RocksDB'] = None,
        allow_update: bool = False
    ) -> bool:
        """注册模型"""
        if db is None:
            raise ValueError("必须提供 db 参数")
        
        collection = collection or cls.DEFAULT_CF
        model_id = cls._resolve_model_id(model_class, model_id)

        meta_key = cls.get_model_key(model_id, collection)
        
        logger.info(f"正在注册模型: {model_id}, 集合: {collection}, 键模式: {key_pattern}")
        logger.info(f"模型类信息: {model_class.__module__}.{model_class.__qualname__}")
        
        # 检查是否已存在
        existing = db.get(cls.MODELS_META_CF, meta_key)
        if existing:
            logger.info(f"发现已存在的模型元数据: {existing}")
            if not allow_update:
                raise ValueError(f"模型 {model_id} 在集合 {collection} 中已存在，如需更新请设置 allow_update=True")
        
        metadata = ModelMetadata(
            model_id=model_id,
            collection=collection,
            key_pattern=key_pattern or KeyPattern.PREFIX_ID_SUFFIX,
            fields=cls._get_model_fields(model_class)
        )
        
        # 使用 model_dump 而不是 dict() 来序列化，并添加 model_class
        metadata_dict = metadata.model_dump(
            exclude_unset=True,
            exclude_none=True,
            mode='json'
        )
        metadata_dict['model_class'] = f"{model_class.__module__}.{model_class.__qualname__}"
        logger.info(f"准备保存模型元数据: {metadata_dict}")
        
        db.set(cls.MODELS_META_CF, meta_key, metadata_dict)
        
        # 确保注册成功
        saved_metadata = db.get(cls.MODELS_META_CF, meta_key)
        if not saved_metadata:
            logger.error(f"模型 {model_id} 注册失败，无法读取保存的元数据")
            raise ValueError(f"模型 {model_id} 注册失败")
        logger.info(f"模型注册成功，保存的元数据: {saved_metadata}")
        
        return True
    
    @classmethod
    def unregister_model(cls,
                        model_class: Optional[Type[BaseModel]] = None,
                        model_id: Optional[str] = None,
                        collection: Optional[str] = None,
                        db: Optional['RocksDB'] = None) -> bool:
        """注销模型"""
        if db is None:
            raise ValueError("必须提供 db 参数")

        model_id = cls._resolve_model_id(model_class, model_id)
        collection = collection or cls.DEFAULT_CF
        meta_key = cls.get_model_key(model_id, collection)
        
        if not db.get(cls.MODELS_META_CF, meta_key):
            raise ValueError(f"模型 {model_id} 在集合 {collection} 中不存在")
        
        return db.delete(cls.MODELS_META_CF, meta_key)
    
    @classmethod
    def update_model(cls,
                    updates: Dict[str, Any],
                    model_class: Optional[Type[BaseModel]] = None,
                    model_id: Optional[str] = None,
                    collection: Optional[str] = None,
                    db: Optional['RocksDB'] = None) -> bool:
        """更新模型元数据"""
        if db is None:
            raise ValueError("必须提供 db 参数")

        model_id = cls._resolve_model_id(model_class, model_id)
        collection = collection or cls.DEFAULT_CF
        meta_key = cls.get_model_key(model_id, collection)
        
        if not db.get(cls.MODELS_META_CF, meta_key):
            raise ValueError(f"模型 {model_id} 在集合 {collection} 中不存在")
        
        metadata = db.get(cls.MODELS_META_CF, meta_key)
        metadata.update(updates)
        metadata['updated_at'] = datetime.utcnow().isoformat()
        
        return db.set(cls.MODELS_META_CF, meta_key, metadata)
    
    @classmethod
    def get_model(cls,
                model_class: Optional[Type[BaseModel]] = None,
                model_id: Optional[str] = None,
                collection: Optional[str] = None,
                db: Optional['RocksDB'] = None) -> Optional[Dict[str, Any]]:
        """获取模型元数据"""
        if db is None:
            raise ValueError("必须提供 db 参数")
        
        model_id = cls._resolve_model_id(model_class, model_id)
        logger.info(f"开始获取模型元数据: model_id={model_id}, collection={collection}")
        
        # 如果没有指定集合，尝试在所有集合中查找
        if collection is None:
            # 先尝试默认集合
            meta_key = cls.get_model_key(model_id, cls.DEFAULT_CF)
            logger.info(f"尝试在默认集合中查找: {meta_key}")
            metadata = db.get(cls.MODELS_META_CF, meta_key)
            if metadata:
                logger.info(f"在默认集合中找到模型: {metadata}")
                return metadata
            
            # 如果在默认集合中找不到，遍历所有集合
            prefix = f"{cls.MODEL_KEY_PREFIX}:"
            logger.info(f"在所有集合中查找，前缀: {prefix}")
            for key in db.iter_keys(cls.MODELS_META_CF, prefix=prefix):
                if key.endswith(f":{model_id}"):
                    metadata = db.get(cls.MODELS_META_CF, key)
                    logger.info(f"在其他集合中找到模型: {key} -> {metadata}")
                    return metadata
            logger.info("在所有集合中都未找到模型")
        else:
            # 如果指定了集合，直接查找
            meta_key = cls.get_model_key(model_id, collection)
            logger.info(f"在指定集合中查找: {meta_key}")
            metadata = db.get(cls.MODELS_META_CF, meta_key)
            if metadata:
                logger.info(f"在指定集合中找到模型: {metadata}")
            else:
                logger.info(f"在指定集合中未找到模型")
            return metadata
        
        return None
    
    @classmethod
    def list_models(cls,
                   db: Optional['RocksDB'] = None) -> Dict[str, Dict[str, Any]]:
        """列出所有模型元数据"""
        if db is None:
            raise ValueError("必须提供 db 参数")
            
        return db.all(collection=cls.MODELS_META_CF)
    
    @classmethod
    def gen_key(cls,
                instance: BaseModel,
                model_id: Optional[str] = None,
                collection: Optional[str] = None,
                db: Optional['RocksDB'] = None,
                **kwargs) -> str:
        """为模型实例生成键"""
        if db is None:
            raise ValueError("必须提供 db 参数")
        
        model_id = cls._resolve_model_id(instance.__class__, model_id)
        collection = collection or cls.DEFAULT_CF
        
        logger.info(f"正在生成键: 模型={model_id}, 集合={collection}, 参数={kwargs}")
        
        # 获取模型元数据
        metadata = cls.get_model(
            instance=instance,
            model_id=model_id,
            collection=collection,
            db=db
        )
        
        if not metadata:
            logger.error(f"模型 {model_id} 在集合 {collection} 中未注册")
            raise ValueError(f"模型 {model_id} 在集合 {collection} 中未注册")
        
        # 获取键模式
        key_pattern = KeyPattern(metadata['key_pattern'])
        
        # 获取 id, infix 和 suffix 值
        try:
            # 获取 ID - 优先使用入参数
            id_value = kwargs.get('id')
            if id_value is None:
                # 其次使用自定义方法
                if hasattr(instance, '__id__'):
                    id_value = instance.__id__()
                else:
                    # 最后使用属性或生成默认值
                    id_value = getattr(instance, 'id', str(uuid.uuid4()))
            
            # 获取中缀 - 优先使用入参数
            infix = kwargs.get('infix')
            if infix is None and key_pattern in [KeyPattern.PREFIX_INFIX_ID, 
                                                KeyPattern.PREFIX_INFIX_ID_SUFFIX,
                                                KeyPattern.PREFIX_INFIX_PATH_VALUE]:
                # 其次使用自定义方法
                if hasattr(instance, '__infix__'):
                    infix = instance.__infix__()
                else:
                    # 最后使用属性
                    infix = getattr(instance, 'infix', None)
                    if infix is None:
                        raise ValueError(
                            "当前键模式需要 'infix' 值。您可以:\n"
                            "1. 在调用时提供 infix 参数\n"
                            "2. 在模型中定义 __infix__() 方法\n"
                            "3. 在模型中定义 infix 属性"
                        )
                
            # 获取后缀 - 优先使用入参数
            suffix = kwargs.get('suffix')
            if suffix is None and key_pattern in [KeyPattern.PREFIX_ID_SUFFIX,
                                                KeyPattern.PREFIX_INFIX_ID_SUFFIX]:
                # 其次使用自定义方法
                if hasattr(instance, '__suffix__'):
                    suffix = instance.__suffix__()
                else:
                    # 最后使用属性或生成默认值
                    suffix = getattr(instance, 'suffix', datetime.utcnow().isoformat())
                
            # 路径和值只支持入参数
            path = kwargs.get('path')
            if path is None and key_pattern in [KeyPattern.PREFIX_PATH_VALUE,
                                                KeyPattern.PREFIX_INFIX_PATH_VALUE]:
                raise ValueError(
                    "当前键模式需要 'path' 值。\n"
                    "请在调用时提供 path 参数"
                )
                
            value = kwargs.get('value')
            if value is None and key_pattern in [KeyPattern.PREFIX_PATH_VALUE,
                                                KeyPattern.PREFIX_INFIX_PATH_VALUE]:
                raise ValueError(
                    "当前键模式需要 'value' 值。\n"
                    "请在调用时提供 value 参数"
                )
            
            # 构建键参数
            key_args = {
                'prefix': model_id,
                'id': id_value,
                'infix': infix,
                'suffix': suffix,
                'path': path,
                'value': value
            }
            logger.info(f"键参数: {key_args}")
            
            # 生成键
            key = KeyPattern.make_key(key_pattern, **key_args)
            logger.info(f"生成的键: {key}")
            return key
            
        except Exception as e:
            logger.error(f"生成键失败: {str(e)}")
            raise
    
    @staticmethod
    def _get_model_fields(model_class: Type[BaseModel]) -> Dict[str, Dict[str, Any]]:
        """获取模型字段定义"""
        fields = {}
        for name, field in model_class.model_fields.items():
            if name not in ['id', 'infix', 'suffix']:
                # 使用 field.annotation 来判断字段是否可选
                is_optional = (
                    getattr(field.annotation, "__origin__", None) is Optional or
                    str(field.annotation).startswith("typing.Optional")
                )
                
                # 确保所有值都是可序列化的
                field_info = {
                    'type': str(field.annotation),
                    'required': not is_optional,
                    'description': field.description or None  # 确保 description 不是 Undefined
                }
                
                # 只有当默认值不是 PydanticUndefined 时才添加
                if not isinstance(field.default, type(PydanticUndefined)):
                    field_info['default'] = field.default
                    
                fields[name] = field_info
                
        return fields 