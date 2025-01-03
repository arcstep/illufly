from typing import Any, Dict, List, Type, Union, Optional, Tuple
from .object_types import (
    TypeHandler, TypeInfo, SimpleTypeHandler, PydanticHandler, DataclassHandler
)
from .path_parser import PathParser, PathSegment
from .path_matcher import PathMatcher
from .type_converter import TypeConverter
from .path_types import PathType, PathInfo
from .exceptions import NotFoundError

import logging
import re

logger = logging.getLogger(__name__)

class ObjectPathRegistry:
    """对象路径注册表 - 管理对象的路径注册和值提取
    
    主要功能:
    1. 注册对象及其所有可能的访问路径
    2. 根据路径提取对象中的值
    3. 验证路径的有效性
    4. 管理不同命名空间下的路径
    
    Usage:
        registry = ObjectPathRegistry()
        
        # 注册对象
        data = {"user": {"name": "test"}, "items": [1, 2, 3]}
        registry.register_object(data, namespace="test")
        
        # 列出所有路径
        paths = registry.list_paths("test")
        # -> ["", "user", "user.name", "items"]
        
        # 提取值
        value = registry.extract(data, "user.name", "test")
        # -> ("test", PathInfo(...))
        
        # 验证路径
        is_valid = registry.validate_path("user.name", "test")
        # -> (True, None, PathInfo(...))
    
    TypeHandler 使用:
        - 自动选择合适的类型处理器
        - 使用处理器生成路径和提取值
        - 支持自定义类型处理器
    
    PathParser 使用:
        - 解析输入的路径字符串
        - 将路径转换为 PathSegment 列表
        - 支持处理复杂的嵌套路径
    """
    
    def __init__(self):
        # 所有对象的访问路径清单
        self._property_paths: Dict[str, Dict[str, PathInfo]] = {}
        # 初始化所有类型处理器
        self._type_handlers: List[TypeHandler] = [
            SimpleTypeHandler(), # 基本类型
            PydanticHandler(),   # Pydantic处理器
            DataclassHandler(),  # dataclass处理器
        ]
        self._parser = PathParser()
        self._matcher = PathMatcher()
        self._converter = TypeConverter()
        self._type_cache: Dict[str, TypeInfo] = {}
    
    def register_object(self, 
                       obj: Union[Type, Any], 
                       namespace: str = None, 
                       path_configs: Dict[str, Dict[str, Any]] = None, 
                       allow_override: bool = False) -> None:
        """注册对象及其所有合法的属性路径"""
        if path_configs is None:
            path_configs = {}
            
        if namespace is None:
            namespace = self._get_default_namespace(obj)
            
        # 1. 找到对应的类型处理器
        handler = self._find_handler(obj)
        if not handler:
            raise ValueError(f"不支持的类型: {type(obj)}")
        
        # 2. 获取类型信息
        type_info = handler.get_type_info(obj)
        
        # 3. 收集所有合法路径
        all_paths = self._collect_nested_paths(obj, handler)
        
        # 4. 注册所有路径
        for path_info in all_paths:
            self.register_path(
                path=path_info.path,
                type_name=path_info.type_name,
                namespace=namespace,
                path_type=path_info.path_type,
                type_info=type_info,
                access_method=path_info.access_method,
                access_path=path_info.access_path,
                **path_configs.get(path_info.path, {})
            )
    
    def validate_path(self, path: str, namespace: str) -> Tuple[bool, Optional[str], Optional[PathInfo]]:
        """验证路径合法性"""
        if namespace not in self._property_paths:
            return False, f"命名空间 '{namespace}' 不存在", None
            
        # 解析并规范化路径
        try:
            segments = self._parser.parse(path)
            normalized_path = self._parser.join_segments(segments)
        except ValueError as e:
            return False, str(e), None
            
        # 尝试直接匹配规范化路径
        if normalized_path in self._property_paths[namespace]:
            return True, None, self._property_paths[namespace][normalized_path]
            
        # 尝试通配符匹配
        wildcard_segments = self._parser.normalize_to_wildcard(segments)
        wildcard_path = self._parser.join_segments(wildcard_segments)
        
        if wildcard_path in self._property_paths[namespace]:
            return True, None, self._property_paths[namespace][wildcard_path]
            
        return False, f"路径 '{path}' 未注册", None
    
    def list_paths(self, namespace: str) -> List[str]:
        """列举命名空间下的所有路径"""
        if namespace not in self._property_paths:
            raise KeyError(f"命名空间 '{namespace}' 不存在")
        return sorted(self._property_paths[namespace].keys())
    
    def get_indexable_paths(self, namespace: str) -> List[str]:
        """获取所有可以建立反向索引的路径"""
        if namespace not in self._property_paths:
            raise KeyError(f"命名空间 '{namespace}' 不存在")
        return sorted(
            path for path, info in self._property_paths[namespace].items()
            if info.path_type == PathType.REVERSIBLE
        )
    
    def extract(self, 
                                obj: Any, 
                                path: str, 
                                namespace: str, 
                                type_name: str = None) -> Tuple[Any, PathInfo]:
        """根据路径提取值并进行类型转换"""
        # 验证路径
        is_valid, error_msg, path_info = self.validate_path(path, namespace)
        if not is_valid:
            raise NotFoundError(error_msg, path, namespace)
            
        try:
            # 获取处理器
            handler = self._find_handler(obj)
            if not handler:
                raise ValueError(f"不支持的类型: {type(obj)}")
                
            # 解析路径
            segments = self._parser.parse(path)
            
            # 逐段提取值
            value = obj
            for segment in segments:
                value = handler.extract_value(value, segment)
                handler = self._find_handler(value)
                if not handler:
                    raise ValueError(f"不支持的类型: {type(value)}")
            
            # 类型转换
            if type_name:
                value = self._converter.convert(value, type_name)
                
            return value, path_info
            
        except Exception as e:
            raise TypeError(str(e), path_info.type_name if path_info else None, type(obj).__name__)
    
    def _collect_nested_paths(self, 
                            obj: Any, 
                            handler: TypeHandler,
                            parent_path: str = "") -> List[PathInfo]:
        """收集对象的所有嵌套路径"""
        logger.info(f"\n=== 开始收集路径 ===")
        logger.info(f"对象类型: {type(obj).__name__}")
        logger.info(f"处理器类型: {type(handler).__name__}")
        logger.info(f"父路径: '{parent_path}'")
        
        all_paths = []
        
        # 获取当前对象的直接路径
        logger.info(f"获取直接路径...")
        direct_paths = handler.get_paths(obj, parent_path)
        logger.info(f"发现 {len(direct_paths)} 条直接路径")
        
        # 转换并添加直接路径
        for path, type_name, path_type, access_method in direct_paths:
            logger.info(f"\n路径详情:")
            logger.info(f"  标准路径: {path}")
            logger.info(f"  类型: {type_name}")
            logger.info(f"  访问方法: {access_method}")
            
            try:
                access_path = self._convert_to_access_path(path, access_method)
                path_info = PathInfo(
                    path=path,
                    access_path=access_path,
                    type_name=type_name,
                    path_type=path_type,
                    access_method=access_method
                )
                all_paths.append(path_info)
                logger.info(f"  访问路径: {access_path}")
                logger.info(f"  转换成功 ✓")
            except Exception as e:
                logger.error(f"  路径转换失败: {str(e)}")
        
        # 获取并处理嵌套字段
        logger.info(f"\n获取嵌套字段...")
        nested_fields = handler.get_nested_fields(obj)
        logger.info(f"发现 {len(nested_fields)} 个嵌套字段")
        
        for field_name, field_obj in nested_fields:
            if field_obj is None:
                logger.info(f"\n字段 '{field_name}' 为空，跳过")
                continue
            
            logger.info(f"\n处理嵌套字段: '{field_name}'")
            logger.info(f"字段类型: {type(field_obj).__name__}")
            
            # 找到嵌套对象的处理器
            nested_handler = self._find_handler(field_obj)
            if not nested_handler:
                logger.warning(f"未找到处理器，跳过字段 '{field_name}'")
                continue
            
            logger.info(f"使用处理器: {type(nested_handler).__name__}")
            
            # 构建嵌套路径
            if parent_path:
                nested_parent = f"{parent_path}{{{field_name}}}"
            else:
                nested_parent = field_name
            logger.info(f"嵌套父路径: '{nested_parent}'")
            
            # 递归处理嵌套对象
            try:
                nested_paths = self._collect_nested_paths(
                    obj=field_obj,
                    handler=nested_handler,
                    parent_path=nested_parent
                )
                logger.info(f"收集到 {len(nested_paths)} 条嵌套路径")
                all_paths.extend(nested_paths)
            except Exception as e:
                logger.error(f"处理嵌套字段 '{field_name}' 时出错: {str(e)}")
        
        logger.info(f"\n=== 路径收集完成 ===")
        logger.info(f"总共收集到 {len(all_paths)} 条路径")
        return all_paths
    
    def _find_handler(self, obj: Any) -> Optional[TypeHandler]:
        """查找合适的类型处理器"""
        for handler in self._type_handlers:
            if handler.can_handle(obj):
                return handler
        return None
    
    def _get_default_namespace(self, obj: Any) -> str:
        """获取默认命名空间"""
        if isinstance(obj, type):
            return obj.__name__
        return obj.__class__.__name__
    
    def get_type_info(self, path: str, namespace: str) -> Optional[TypeInfo]:
        """获取路径的类型信息"""
        path_info = self.get_path_info(path, namespace)
        if path_info:
            return path_info.type_info
        return None
    
    def get_container_info(self, path: str, namespace: str) -> Optional[Tuple[str, str]]:
        """获取容器类型的元素类型信息
        
        Returns:
            Optional[Tuple[str, str]]: (容器类型, 元素类型)
        """
        type_info = self.get_type_info(path, namespace)
        if type_info and type_info.is_container:
            return (type_info.type_name, type_info.element_type)
        return None
    
    def register_path(self,
                     path: str,
                     type_name: str,
                     namespace: str,
                     path_type: PathType,
                     type_info: TypeInfo,
                     **config) -> None:
        """注册单个路径"""
        # 确保命名空间存在
        if namespace not in self._property_paths:
            self._property_paths[namespace] = {}
        
        # 解析路径并重新生成规范化的路径字符串
        parsed_segments = self._parser.parse(path) if path else []
        normalized_path = self._parser.join_segments(parsed_segments)
        
        # 创建路径信息
        path_info = PathInfo(
            path=normalized_path,  # 使用规范化的路径
            type_name=type_name,
            path_type=path_type,
            parsed_segments=parsed_segments,
            type_info=type_info,
            is_tag_list=config.get('is_tag_list', False),
            max_tags=config.get('max_tags', 100),
            description=config.get('description', '')
        )
        
        # 注册路径信息
        self._property_paths[namespace][normalized_path] = path_info
    
    def _normalize_path_to_wildcard(self, path: str) -> str:
        """将路径中的具体索引/键转换为通配符形式"""
        # 替换列表索引 [0] -> [*]
        path = re.sub(r'\[\d+\]', '[*]', path)
        # 替换字典键 {"key"} -> {*}
        path = re.sub(r'\{[^}]+\}', '{*}', path)
        return path
    
    def _convert_to_access_path(self, path: str, access_method: str) -> str:
        """转换为实际访问路径
        
        Args:
            path: 标准化路径（使用花括号语法）
            access_method: 访问方法 ("dot"/"bracket"/"list")
            
        Returns:
            实际访问路径
        """
        if not path:  # 处理根路径
            return path
        
        if access_method == "dot":
            return path
        elif access_method == "bracket":
            # 将 {key} 转换为 ['key']
            return re.sub(r'\{([^}]+)\}', r"['\1']", path)
        elif access_method == "list":
            # 保持 [index] 格式不变
            return path
        else:
            raise ValueError(f"不支持的访问方法: {access_method}")