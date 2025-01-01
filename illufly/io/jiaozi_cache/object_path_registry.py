from typing import Any, Dict, List, Type, Union, Optional, Tuple, Set, Callable
from enum import Enum
import re
from pydantic import BaseModel
from dataclasses import dataclass
import msgpack
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from typing import get_origin, get_args
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class PathType(Enum):
    """路径类型"""
    INDEXABLE = "indexable"    # 可索引路径，指向基础类型值
    STRUCTURAL = "structural"  # 结构路径，指向复合类型，不用于索引

@dataclass
class TypeMetadata:
    """类型元数据"""
    type_class: Type
    constructor: Optional[Callable] = None  # 构造函数，用于实例化对象
    validator: Optional[Callable] = None    # 验证函数，用于验证数据
    to_dict: Optional[Callable] = None      # 对象转字典方法
    from_dict: Optional[Callable] = None    # 字典转对象方法

class PathTypeInfo:
    """路径类型信息"""
    def __init__(self,
                 path: str,
                 type_name: str,
                 path_type: PathType,
                 type_metadata: Optional[TypeMetadata] = None,
                 is_tag_list: bool = False,
                 max_tags: int = 100,
                 description: str = "",
                 model_class: Optional[Type] = None,
                 is_tuple: bool = False) -> None:
        self.path = path
        self.type_name = type_name
        self.path_type = path_type
        self.is_tag_list = is_tag_list
        self.max_tags = max_tags
        self.description = description
        self.is_tuple = is_tuple
        
        # 如果提供了 model_class，创建对应的 TypeMetadata
        if model_class is not None:
            self.type_metadata = TypeMetadata(
                type_class=model_class,
                constructor=model_class,
                to_dict=(lambda x: x.model_dump() 
                        if hasattr(x, 'model_dump') 
                        else vars(x)),
                validator=lambda x: isinstance(x, dict)
            )
        else:
            self.type_metadata = type_metadata

    @property
    def model_class(self) -> Optional[Type]:
        """兼容旧版 API"""
        return (self.type_metadata.type_class 
                if self.type_metadata and issubclass(self.type_metadata.type_class, BaseModel)
                else None)

    @property
    def is_indexable(self) -> bool:
        """是否可以建立反向索引"""
        return self.path_type == PathType.INDEXABLE

    @property
    def is_model(self) -> bool:
        """是否为 Pydantic 模型"""
        return self.model_class is not None and issubclass(self.model_class, BaseModel)

class PathError(Exception):
    """路径相关错误的基类"""
    pass

class PathNotFoundError(Exception):
    """路径未找到错误"""
    def __init__(self, message: str, invalid_part: str, namespace: str):
        super().__init__(message)
        self.invalid_part = invalid_part
        self.namespace = namespace

class PathTypeError(PathError):
    """路径类型错误"""
    def __init__(self, path: str, expected_type: str, actual_type: str):
        self.path = path
        self.expected_type = expected_type
        self.actual_type = actual_type
        super().__init__(f"路径 '{path}' 期望类型为 {expected_type}，实际类型为 {actual_type}")

class PathValidationError(PathError):
    """路径验证错误"""
    pass

class ObjectPathRegistry:
    """路径和类型管理器"""
    
    BUILTIN_NAMESPACE = "__built_in__"
    
    # 内置支持的类型
    BUILTIN_TYPES = {
        # 基础类型
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        
        # 集合类型
        "tuple": tuple,
        "list": list,
        "dict": dict,
        "set": set,
        "frozenset": frozenset,
        
        # 日期时间类型
        "datetime": datetime,
        "date": datetime.date,
        "time": datetime.time,
        
        # 其他常用类型
        "Decimal": Decimal,
        "UUID": UUID,
        "Path": Path,
    }

    # 可索引的基础类型
    INDEXABLE_TYPES = {
        str: "str",
        int: "int",
        float: "float",
        bool: "bool",
        bytes: "bytes",
    }

    ROOT_PATH = ""  # 定义根路径常量

    def __init__(self):
        """初始化路径类型管理器"""
        self._path_types: Dict[str, Dict[str, PathTypeInfo]] = {}
        self._type_registry: Dict[str, Callable] = {
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "bytes": bytes,
        }
    
    def _get_path_type(self, field_type: Any) -> PathType:
        """获取字段的路径类型
        
        结构类型包括：
        1. Pydantic 模型
        2. 字典类型
        3. 包含结构类型的列表
        
        可索引类型包括：
        1. 基本类型 (str, int, float 等)
        2. 包含基本类型的列表
        """
        # 处理 None 类型
        if field_type is None:
            return PathType.INDEXABLE
            
        # 获取原始类型
        origin_type = get_origin(field_type)
        
        # 处理 Pydantic 模型
        if isinstance(field_type, type) and issubclass(field_type, BaseModel):
            return PathType.STRUCTURAL
            
        # 处理字典类型
        if origin_type in (dict, Dict):
            return PathType.STRUCTURAL
            
        # 处理列表类型
        if origin_type in (list, List):
            args = get_args(field_type)
            if not args:  # 如果没有类型参数，默认为可索引
                return PathType.INDEXABLE
                
            element_type = args[0]
            # 如果列表元素是结构类型，则整个列表也是结构类型
            if (isinstance(element_type, type) and issubclass(element_type, BaseModel)) or \
               get_origin(element_type) in (dict, Dict):
                return PathType.STRUCTURAL
            return PathType.INDEXABLE
            
        # 其他类型都视为可索引
        return PathType.INDEXABLE

    def get_indexable_paths(self, namespace: str) -> List[str]:
        """获取指定命名空间中的所有可索引路径"""
        if namespace not in self._path_types:
            return []
            
        return [
            path for path, info in self._path_types[namespace].items()
            if info.path_type == PathType.INDEXABLE
        ]
    
    def register_path(self,
                     path: str,
                     type_name: str,
                     namespace: str,
                     path_type: PathType,
                     type_metadata: Optional[TypeMetadata] = None,
                     is_tag_list: bool = False,
                     max_tags: int = 100,
                     description: str = "") -> None:
        """注册单个路径
        
        Args:
            path: 路径字符串
            type_name: 类型名称
            namespace: 命名空间
            path_type: 路径类型
            type_metadata: 类型元数据（可选）
            is_tag_list: 是否为标签列表
            max_tags: 标签列表最大长度
            description: 路径描述
            
        Raises:
            PathValidationError: 路径验证失败
        """
        # 基本验证
        if path is None:
            raise PathValidationError("路径不能为 None")
        if not namespace:
            raise PathValidationError("命名空间不能为空")
            
        # 标签列表验证
        if is_tag_list:
            if path_type != PathType.INDEXABLE:
                raise PathValidationError(f"标签列表路径 '{path}' 必须是可索引类型")
            if type_name not in ('str', 'List[str]', 'list'):
                raise PathValidationError(f"标签列表路径 '{path}' 的元素类型必须是字符串")

        # 确保命名空间存在
        if namespace not in self._path_types:
            self._path_types[namespace] = {}

        # 注册路径信息
        self._path_types[namespace][path] = PathTypeInfo(
            path=path,
            type_name=type_name,
            path_type=path_type,
            type_metadata=type_metadata,
            is_tag_list=is_tag_list,
            max_tags=max_tags,
            description=description
        )
    
    def _register_nested_fields(self, 
                              obj: Any, 
                              parent_path: str,
                              namespace: str,
                              path_configs: Dict[str, Dict[str, Any]]) -> None:
        """递归注册嵌套字段"""
        if isinstance(obj, dict):
            for key, value in obj.items():
                field_path = f"{parent_path}.{key}" if parent_path else key
                
                # 获取字段配置
                config = path_configs.get(field_path, {})
                is_tag_list = config.get("is_tag_list", False)
                
                # 确定路径类型
                if is_tag_list:
                    if not isinstance(value, (list, tuple)) or not all(isinstance(x, str) for x in value):
                        raise PathValidationError(f"标签列表 {field_path} 必须是字符串列表")
                    path_type = PathType.INDEXABLE
                else:
                    path_type = self._get_path_type(type(value))
                
                # 注册当前字段
                self.register_path(
                    path=field_path,
                    type_name=config.get("type_name", type(value).__name__),
                    namespace=namespace,
                    path_type=path_type,
                    is_tag_list=is_tag_list,
                    max_tags=config.get("max_tags", 100),
                    description=config.get("description", ""),
                    model_class=None,
                    is_tuple=False
                )
                
                # 处理嵌套字段
                if isinstance(value, (dict, BaseModel)):
                    nested_config = config.get("nested", {})
                    self._register_nested_fields(value, field_path, namespace, nested_config)
    
    def _get_default_namespace(self, obj: Any) -> str:
        """从对象获取默认命名空间名称"""
        if isinstance(obj, type):
            return obj.__name__
        return obj.__class__.__name__

    def unregister_namespace(self, namespace: str) -> None:
        """注销指定命名空间的所有注册
        
        Args:
            namespace: 要注销的命名空间
            
        Raises:
            KeyError: 如果命名空间不存在
        """
        if namespace not in self._path_types:
            raise KeyError(f"命名空间 '{namespace}' 不存在")
        del self._path_types[namespace]

    def register_object(self,
                       obj: Union[Type, Any],
                       namespace: str = None,
                       path_configs: Dict[str, Dict[str, Any]] = None,
                       allow_override: bool = False) -> None:
        """注册对象类型"""
        if path_configs is None:
            path_configs = {}

        # 确定命名空间
        if namespace is None:
            namespace = self._get_default_namespace(obj)

        # 检查命名空间是否已存在
        if not allow_override and namespace in self._path_types:
            raise ValueError(
                f"命名空间 '{namespace}' 已存在。如需重新注册，请先使用 unregister_namespace() 注销该命名空间。"
            )

        # 初始化或清理命名空间
        if allow_override and namespace in self._path_types:
            self._path_types[namespace].clear()
        else:
            self._path_types[namespace] = {}

        # 处理 Pydantic 模型
        if hasattr(obj, 'model_fields') or (isinstance(obj, type) and hasattr(obj, 'model_fields')):
            self._register_model_fields(obj, "", namespace, path_configs)
        # 处理字典类型
        elif isinstance(obj, dict):
            self._register_dict_structure(obj, "", namespace, path_configs)

    def _get_nested_list_type_name(self, field_type: Any) -> str:
        """递归获取嵌套列表的类型名称"""
        origin = get_origin(field_type)
        if origin not in (list, List):
            return getattr(field_type, '__name__', str(field_type))
        
        args = get_args(field_type)
        if not args:
            return "List[Any]"
        
        element_type = args[0]
        inner_type_name = self._get_nested_list_type_name(element_type)
        return f"List[{inner_type_name}]"

    def _register_model_fields(self,
                             model: Union[Type[BaseModel], BaseModel],
                             parent_path: str,
                             namespace: str,
                             path_configs: Dict[str, Dict[str, Any]]) -> None:
        """从 Pydantic 模型注册字段"""
        model_class = model if isinstance(model, type) else model.__class__
        logger.info("开始注册模型 %s 的字段", model_class.__name__)
        
        # 注册模型本身，包括 type_metadata
        self.register_path(
            path=parent_path or self.ROOT_PATH,
            type_name=model_class.__name__,
            namespace=namespace,
            path_type=PathType.STRUCTURAL,
            type_metadata=TypeMetadata(
                type_class=model_class,
                constructor=model_class.model_validate,
                to_dict=lambda x: x.model_dump(),
                validator=lambda x: isinstance(x, dict)
            )
        )

        # 处理字段
        for field_name, field in model_class.model_fields.items():
            field_path = f"{parent_path}.{field_name}" if parent_path else field_name
            field_config = path_configs.get(field_name, {})
            field_type = field.annotation
            
            # 处理嵌套模型
            if isinstance(field_type, type) and issubclass(field_type, BaseModel):
                self._register_model_fields(
                    field_type,
                    field_path,
                    namespace,
                    field_config.get('nested', {})
                )
            else:
                # 获取类型名称
                if field_config.get('type_name'):
                    type_name = field_config['type_name']
                else:
                    type_name = self._get_nested_list_type_name(field_type)
                
                logger.info("字段 %s: 最终类型名称=%s", field_name, type_name)
                
                # 确定路径类型
                path_type = self._get_path_type(field_type)
                
                # 处理标签列表
                is_tag_list = field_config.get('is_tag_list', False)
                if is_tag_list:
                    if not (get_origin(field_type) in (list, List) and get_args(field_type)[0] == str):
                        raise PathValidationError(f"标签列表字段 '{field_path}' 的元素类型必须是字符串")
                    path_type = PathType.INDEXABLE

                self.register_path(
                    path=field_path,
                    type_name=type_name,
                    namespace=namespace,
                    path_type=path_type,
                    is_tag_list=is_tag_list,
                    max_tags=field_config.get('max_tags', 100)
                )

    def _register_annotated_fields(self,
                                 cls: Type,
                                 parent_path: str,
                                 namespace: str,
                                 path_configs: Dict[str, Dict[str, Any]]) -> None:
        """从类型注解注册字段"""
        if hasattr(cls, "__annotations__"):
            for field_name, field_type in cls.__annotations__.items():
                field_path = f"{parent_path}.{field_name}" if parent_path else field_name
                
                # 获取字段配置
                config = path_configs.get(field_path, {})
                
                # 注册当前字段
                self.register_path(
                    path=field_path,
                    type_name=config.get("type_name", getattr(field_type, "__name__", str(field_type))),
                    namespace=namespace,
                    path_type=self._get_path_type(field_type),
                    is_tag_list=config.get("is_tag_list", False),
                    max_tags=config.get("max_tags", 100),
                    description=config.get("description", "")
                )
    
    def _register_dict_fields(self,
                             obj: Dict,
                             parent_path: str,
                             namespace: str,
                             path_configs: Dict[str, Dict[str, Any]]) -> None:
        """从字典注册字段"""
        for key, value in obj.items():
            field_path = f"{parent_path}.{key}" if parent_path else key
            
            # 获取字段配置
            config = path_configs.get(key, {})
            is_tag_list = config.get("is_tag_list", False)
            
            # 确定路径类型
            path_type = self._get_path_type(type(value))
            
            # 获取类型名称
            if config.get('type_name'):
                type_name = config['type_name']
            else:
                if isinstance(value, list):
                    if value and all(isinstance(x, str) for x in value):
                        type_name = "List[str]"
                    else:
                        type_name = "List[Any]"
                else:
                    type_name = type(value).__name__
            
            logger.info("注册字段 %s: 类型=%s, 是否标签列表=%s, 最大标签数=%s",
                       field_path, type_name, is_tag_list, config.get('max_tags', 100))
            
            # 注册当前字段
            self.register_path(
                path=field_path,
                type_name=type_name,
                namespace=namespace,
                path_type=path_type,
                is_tag_list=is_tag_list,
                max_tags=config.get("max_tags", 100),
                description=config.get("description", "")
            )
            
            # 处理嵌套字段
            if isinstance(value, dict):
                nested_config = config.get("nested", {})
                self._register_dict_fields(value, field_path, namespace, nested_config)

    def _extract_inner_type(self, type_name: str, access_depth: int) -> str:
        """从嵌套类型名称中提取内部类型
        
        Args:
            type_name: 类型名称，如 "List[List[str]]"
            access_depth: 访问深度，如 "list[0][1]" 的深度为 2
            
        Returns:
            内部类型名称
        """
        if not type_name.startswith('List['):
            return type_name
        
        current_type = type_name
        for _ in range(access_depth):
            if not current_type.startswith('List['):
                break
            current_type = current_type[5:-1]  # 移除 "List[" 和 "]"
        
        return current_type

    def extract_and_convert_value(self, obj: Any, path: str, namespace: str, type_name: str = None) -> Tuple[Any, PathTypeInfo]:
        """提取并转换路径值"""
        if namespace not in self._path_types:
            raise PathNotFoundError(f"找不到命名空间 '{namespace}'", "", namespace)
        
        base_path = path.split('[')[0] if '[' in path else path
        if base_path not in self._path_types[namespace]:
            raise PathNotFoundError(f"找不到路径 '{path}'", base_path, namespace)

        path_info = self._path_types[namespace][base_path]
        logger.info("路径类型信息: %s", {
            'type_name': path_info.type_name,
            'path_type': path_info.path_type,
            'is_tag_list': path_info.is_tag_list,
            'max_tags': path_info.max_tags
        })
        
        try:
            # 检查是否尝试对非列表类型使用索引访问
            if '[' in path:
                type_name = path_info.type_name.lower()
                if not (type_name.startswith(('list[', 'dict[', 'tuple[')) or type_name in ('list', 'dict', 'tuple')):
                    raise PathTypeError(
                        f"无法对类型 {path_info.type_name} 使用数组索引",
                        expected_type="list/tuple/dict",
                        actual_type=path_info.type_name
                    )
            
            value = self._get_value_from_path(obj, path)
            logger.info("提取的原始值: %s (%s)", value, type(value).__name__)
            
            # 类型转换
            if path_info.type_name == 'float' and isinstance(value, int):
                value = float(value)
            elif path_info.type_name == 'int' and isinstance(value, str):
                try:
                    value = int(value)
                except ValueError:
                    raise PathTypeError(f"无法将字符串转换为整数", "int", "str")
            
            # 检查结构类型访问
            if path_info.path_type == PathType.STRUCTURAL and not '[' in path:
                raise PathTypeError(f"不能直接访问结构类型", "indexable", "structural")
            
        except PathValidationError:
            raise
        except PathTypeError:
            raise
        except (AttributeError, KeyError, IndexError) as e:
            raise PathValidationError(f"无法访问路径 '{path}': {str(e)}")

        # 处理列表元素访问
        if '[' in path:
            if path_info.type_name.startswith('List['):
                # 计算访问深度
                access_depth = len(re.findall(r'\[([^\]]*)\]', path))
                inner_type = self._extract_inner_type(path_info.type_name, access_depth)
                logger.info("处理列表元素访问, 元素类型=%s", inner_type)
                
                # 如果还有点号访问，说明是访问结构体的字段
                if '.' in path:
                    field_path = path.split('.')[-1]
                    if isinstance(value, BaseModel):
                        field_info = value.model_fields.get(field_path)
                        if field_info:
                            field_type = field_info.annotation
                            if hasattr(field_type, 'model_fields'):
                                inner_type = field_type.__name__
                            elif get_origin(field_type) in (list, List):
                                args = get_args(field_type)
                                if args:
                                    inner_type = f"List[{args[0].__name__}]"
                        else:
                            inner_type = getattr(field_type, '__name__', str(field_type))
                    elif isinstance(value, str):
                        inner_type = 'str'
                    elif isinstance(value, list):
                        # 如果值是列表，尝试从第一个元素推断类型
                        if value and isinstance(value[0], int):
                            inner_type = 'List[int]'
                        elif value and isinstance(value[0], str):
                            inner_type = 'List[str]'
                
                return value, PathTypeInfo(
                    path=path_info.path,
                    type_name=inner_type,
                    path_type=PathType.INDEXABLE,
                    type_metadata=path_info.type_metadata,
                    is_tag_list=False,
                    max_tags=path_info.max_tags,
                    description=path_info.description
                )

        # 处理标签列表
        if path_info.is_tag_list and isinstance(value, list):
            if len(value) > path_info.max_tags:
                value = value[:path_info.max_tags]
                logger.info("标签列表已截断至 %d 个元素", path_info.max_tags)

        return value, path_info

    def _get_value_from_path(self, obj: Any, path: str) -> Any:
        """从路径获取值"""
        if not path:
            return obj

        parts = path.split('.')
        current = obj

        try:
            for part in parts:
                if '[' in part:
                    # 处理数组索引
                    base = part[:part.index('[')]
                    indices = re.findall(r'\[([^\]]*)\]', part)
                    
                    # 先获取基础属性
                    if base:
                        if isinstance(current, dict):
                            current = current[base]
                        else:
                            current = getattr(current, base)
                    
                    # 依次处理所有索引
                    for idx in indices:
                        try:
                            index = int(idx)
                            if not isinstance(current, (list, tuple)):
                                raise PathValidationError(
                                    f"无法对类型 {type(current).__name__} 使用数组索引"
                                )
                            if not (0 <= index < len(current)):
                                raise PathValidationError(f"索引 {index} 超出范围")
                            current = current[index]
                        except ValueError:
                            raise PathValidationError(f"无效的数组索引: {idx}")
                else:
                    if isinstance(current, dict):
                        current = current[part]
                    else:
                        current = getattr(current, part)
        except (AttributeError, KeyError) as e:
            raise PathNotFoundError(f"找不到路径 '{path}'", str(e), "")

        return current

    def _get_type_name(self, obj: Any) -> str:
        """获取对象的类型名称"""
        if isinstance(obj, type):
            return obj.__name__
        return obj.__class__.__name__

    def _register_complex_value(self,
                              value: Union[dict, list],
                              path: str,
                              namespace: str,
                              path_config: Dict[str, Any]) -> None:
        """注册复杂值类型（字典或列表）"""
        if isinstance(value, dict):
            self.register_path(
                path=path,
                type_name="dict",
                namespace=namespace,
                path_type=PathType.STRUCTURAL
            )
            for key, sub_value in value.items():
                sub_path = f"{path}.{key}" if path else key
                if isinstance(sub_value, (dict, list)):
                    self._register_complex_value(
                        sub_value,
                        sub_path,
                        namespace,
                        path_config.get(key, {})
                    )
        elif isinstance(value, list) and value:
            sample = value[0]
            if isinstance(sample, (dict, list)):
                self._register_complex_value(
                    sample,
                    f"{path}[*]" if path else "*",
                    namespace,
                    path_config
                )

    def _register_dict_structure(self,
                               data: Dict,
                               parent_path: str,
                               namespace: str,
                               path_configs: Dict[str, Dict[str, Any]]) -> None:
        """注册字典结构，包括所有嵌套路径"""
        for key, value in data.items():
            current_path = f"{parent_path}.{key}" if parent_path else key
            # 获取当前路径的配置
            config = path_configs.get(key, {})
            # 获取配置的类型名称，如果没有则使用值的实际类型
            type_name = config.get('type_name', type(value).__name__)
            
            if isinstance(value, dict):
                self.register_path(
                    path=current_path,
                    type_name=type_name,
                    namespace=namespace,
                    path_type=PathType.STRUCTURAL
                )
                self._register_dict_structure(value, current_path, namespace, config)
                
            elif isinstance(value, list):
                # 检查是否为标签列表
                is_tag_list = config.get('is_tag_list', False)
                max_tags = config.get('max_tags', 100)
                
                self.register_path(
                    path=current_path,
                    type_name=type_name,
                    namespace=namespace,
                    path_type=PathType.INDEXABLE,
                    is_tag_list=is_tag_list,
                    max_tags=max_tags
                )
                
                if value and not is_tag_list:  # 如果不是标签列表才注册子路径
                    for i, item in enumerate(value):
                        index_path = f"{current_path}[{i}]"
                        if isinstance(item, dict):
                            self.register_path(
                                path=index_path,
                                type_name="dict",
                                namespace=namespace,
                                path_type=PathType.STRUCTURAL
                            )
                            self._register_dict_structure(item, index_path, namespace, config)
                        else:
                            self.register_path(
                                path=index_path,
                                type_name=type_name,
                                namespace=namespace,
                                path_type=PathType.INDEXABLE
                            )
                    
                    if isinstance(value[0], dict):
                        wildcard_path = f"{current_path}[*]"
                        self.register_path(
                            path=wildcard_path,
                            type_name="dict",
                            namespace=namespace,
                            path_type=PathType.STRUCTURAL
                        )
                        self._register_dict_structure(value[0], wildcard_path, namespace, config)
                        
            else:
                # 注册基本类型，使用配置的类型名称
                self.register_path(
                    path=current_path,
                    type_name=type_name,
                    namespace=namespace,
                    path_type=PathType.INDEXABLE,
                    **{k: v for k, v in config.items() if k not in ('type_name',)}
                )
