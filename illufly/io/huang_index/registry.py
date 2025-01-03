from typing import Dict, Type
from .model import HuangIndexModel

class ModelRegistry:
    """模型注册表"""
    _models: Dict[str, Type[HuangIndexModel]] = {}
    
    @classmethod
    def register(cls, model_class: Type[HuangIndexModel]) -> None:
        """注册模型类"""
        cls._models[model_class.__name__] = model_class
    
    @classmethod
    def get(cls, name: str) -> Type[HuangIndexModel]:
        """获取模型类"""
        return cls._models[name] 