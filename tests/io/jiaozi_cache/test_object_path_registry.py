from typing import List, Dict, Any, Optional
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pathlib import Path
import pytest
from pydantic import BaseModel
from dataclasses import dataclass
from illufly.io.jiaozi_cache import (
    ObjectPathRegistry,
    PathTypeInfo,
    PathNotFoundError,
    PathValidationError,
    PathTypeError,
    PathType
)
import logging

# 配置日志
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 测试用的类型定义
class SimpleModel(BaseModel):
    """简单模型，用于基础测试"""
    name: str
    value: int

@pytest.fixture
def manager():
    """创建管理器"""
    return ObjectPathRegistry()

@pytest.fixture
def complex_data():
    """创建复杂测试数据"""
    return {
        "string": "hello",
        "number": 42,
        "nested": {
            "coordinates": [1, 2, 3],
            "point": {"x": 10, "y": 20}
        },
        "arrays": {
            "simple": [1, 2, 3],
            "objects": [
                {"id": 1, "name": "first"},
                {"id": 2, "name": "second"}
            ]
        }
    }

def test_register_object(manager):
    """测试对象注册"""
    class UserModel(BaseModel):
        name: str
        age: int

    # 测试类注册
    manager.register_object(UserModel)
    assert "UserModel" in manager._path_types
    
    # 测试实例注册 - 修复参数
    user = UserModel(name="test", age=123)
    manager.register_object(user, namespace="UserInstance")
    assert "UserInstance" in manager._path_types
    assert "" in manager._path_types["UserInstance"]
    assert "name" in manager._path_types["UserInstance"]
    assert "age" in manager._path_types["UserInstance"]

def test_extract_basic_values(manager, complex_data):
    """测试基础值提取"""
    manager.register_object(complex_data, namespace="root")
    
    test_cases = [
        ("string", "hello"),
        ("number", 42),
        ("nested.coordinates[0]", 1),
        ("nested.point.x", 10),
        ("arrays.objects[1].name", "second"),
    ]
    
    for path, expected in test_cases:
        value, _ = manager.extract_and_convert_value(complex_data, path, namespace="root")
        assert value == expected

def test_extract_with_type_conversion(manager, complex_data):
    """测试类型转换"""
    manager.register_object(
        complex_data,
        namespace="root",
        path_configs={
            "number": {"type_name": "float"}
        }
    )
    
    value, _ = manager.extract_and_convert_value(complex_data, "number", namespace="root")
    assert isinstance(value, float)
    assert value == 42.0

def test_extract_tag_list(manager):
    """测试标签列表"""
    data = {"tags": ["tag1", "tag2", "tag3"]}
    
    manager.register_object(
        data,
        namespace="test",
        path_configs={
            "tags": {
                "is_tag_list": True,
                "max_tags": 2
            }
        }
    )
    
    value, _ = manager.extract_and_convert_value(data, "tags", namespace="test")
    assert value == ["tag1", "tag2"]

def test_register_nested_model(manager):
    """测试嵌套模型注册"""
    class Address(BaseModel):
        street: str
        city: str
        
    class User(BaseModel):
        name: str
        address: Address
        
    manager.register_object(User)
    
    # 验证路径注册
    assert "" in manager._path_types["User"]  # 根路径
    assert "name" in manager._path_types["User"]
    assert "address" in manager._path_types["User"]
    assert "address.street" in manager._path_types["User"]
    assert "address.city" in manager._path_types["User"]
    
    # 验证类型信息
    assert manager._path_types["User"][""].type_metadata is not None
    assert manager._path_types["User"]["address"].type_metadata is not None

def test_error_handling(manager, complex_data):
    """测试错误处理"""
    manager.register_object(complex_data, namespace="test_root")
    
    # 测试无效路径
    with pytest.raises(PathNotFoundError) as exc_info:
        manager.extract_and_convert_value(complex_data, "invalid.path", namespace="test_root")
    assert "invalid" in str(exc_info.value)
    
    # 测试类型转换失败 - 使用新的命名空间
    manager.register_object(
        complex_data,
        namespace="test_root_2",
        path_configs={
            "string": {"type_name": "int"}
        }
    )
    with pytest.raises(PathTypeError) as exc_info:
        manager.extract_and_convert_value(complex_data, "string", namespace="test_root_2")
    assert "期望类型为 int" in str(exc_info.value)

def test_register_dict_structure(manager):
    """测试字典结构注册"""
    data = {
        "user": {
            "name": "test",
            "scores": [
                {"subject": "math", "value": 90},
                {"subject": "english", "value": 85}
            ]
        }
    }
    
    manager.register_object(data, namespace="Config")
    
    # 验证路径注册
    assert "user" in manager._path_types["Config"]
    assert "user.name" in manager._path_types["Config"]
    assert "user.scores[*].subject" in manager._path_types["Config"]
    assert "user.scores[*].value" in manager._path_types["Config"]
    
    # 验证路径类型
    assert manager._path_types["Config"]["user"].path_type == PathType.STRUCTURAL
    assert manager._path_types["Config"]["user.name"].path_type == PathType.INDEXABLE
    assert manager._path_types["Config"]["user.scores[*].subject"].path_type == PathType.INDEXABLE

def test_tag_list_validation(manager):
    """测试标签列表验证"""
    class TagModel(BaseModel):
        tags: List[str]
        items: List[Dict[str, str]]  # 不能作为标签列表
    
    # 测试有效的标签列表配置
    manager.register_object(
        TagModel,
        path_configs={
            "tags": {
                "is_tag_list": True,
                "max_tags": 2
            }
        }
    )
    
    assert manager._path_types["TagModel"]["tags"].is_tag_list
    assert manager._path_types["TagModel"]["tags"].max_tags == 2
    
    # 测试无效的标签列表配置
    with pytest.raises(PathValidationError):
        manager.register_object(
            TagModel,
            namespace="InvalidTags",
            path_configs={
                "items": {
                    "is_tag_list": True
                }
            }
        )

def test_override_registration(manager):
    """测试覆盖注册"""
    class SimpleModel(BaseModel):
        value: int

    # 首次注册
    manager.register_object(SimpleModel)
    
    # 不允许覆盖时应该失败
    with pytest.raises(ValueError):
        manager.register_object(SimpleModel)
    
    # 允许覆盖时应该成功
    manager.register_object(SimpleModel, allow_override=True)
    
    # 使用不同命名空间应该成功
    manager.register_object(SimpleModel, namespace="Custom")

def test_path_type_detection(manager):
    """测试路径类型检测"""
    class ComplexModel(BaseModel):
        name: str  # 可索引
        data: Dict[str, Any]  # 结构类型
        items: List[str]  # 可索引
        nested: List[Dict[str, Any]]  # 结构类型
    
    manager.register_object(ComplexModel, namespace="TestComplex")
    
    assert manager._path_types["TestComplex"]["name"].path_type == PathType.INDEXABLE
    assert manager._path_types["TestComplex"]["data"].path_type == PathType.STRUCTURAL
    assert manager._path_types["TestComplex"]["items"].path_type == PathType.INDEXABLE
    assert manager._path_types["TestComplex"]["nested"].path_type == PathType.STRUCTURAL

def test_path_validation_errors(manager):
    """测试路径验证错误"""
    class User(BaseModel):
        name: str
        scores: List[int]
    
    user = User(name="test", scores=[1, 2, 3])
    manager.register_object(user)
    
    # 测试无效路径
    with pytest.raises(PathNotFoundError) as exc_info:
        manager.extract_and_convert_value(user, "invalid.path", namespace="User")
    assert "找不到路径" in str(exc_info.value)
    
    # 测试无效索引
    with pytest.raises(PathValidationError) as exc_info:
        manager.extract_and_convert_value(user, "scores[invalid]", namespace="User")
    assert "无效的数组索引" in str(exc_info.value)
    
    # 测试索引越界
    with pytest.raises(PathValidationError) as exc_info:
        manager.extract_and_convert_value(user, "scores[10]", namespace="User")
    assert "超出范围" in str(exc_info.value)
    
    # 测试类型错误
    with pytest.raises(PathTypeError) as exc_info:
        manager.extract_and_convert_value(user, "name[0]", namespace="User")
    assert "期望类型为 list/tuple" in str(exc_info.value)

def test_path_registration_validation(manager):
    """测试路径注册验证"""
    # 测试 None 路径
    with pytest.raises(PathValidationError) as exc_info:
        manager.register_path(
            path=None,
            type_name="str",
            namespace="test",
            path_type=PathType.INDEXABLE
        )
    assert "路径不能为 None" in str(exc_info.value)

    # 测试根路径可以是任何类型
    # 简单值
    manager.register_path(
        path="",
        type_name="str",
        namespace="test1",
        path_type=PathType.INDEXABLE
    )

    # 复合结构
    manager.register_path(
        path="",
        type_name="dict",
        namespace="test2",
        path_type=PathType.STRUCTURAL
    )

    # 集合类型
    manager.register_path(
        path="",
        type_name="list",
        namespace="test3",
        path_type=PathType.INDEXABLE
    )

def test_indexable_paths(manager):
    """测试可索引路径识别"""
    class Address(BaseModel):
        street: str          # 可索引
        number: int         # 可索引
        location: Dict[str, float]  # 结构类型
        
    class User(BaseModel):
        name: str           # 可索引
        age: int           # 可索引
        scores: List[int]   # 可索引（基础类型列表）
        tags: List[str]     # 可索引（标签列表）
        address: Address    # 结构类型
        friends: List[Address]  # 结构类型
    
    manager.register_object(User)
    
    # 获取所有可索引路径
    indexable_paths = manager.get_indexable_paths("User")
    
    # 验证可索引路径
    assert "name" in indexable_paths
    assert "age" in indexable_paths
    assert "scores" in indexable_paths
    assert "tags" in indexable_paths
    assert "address.street" in indexable_paths
    assert "address.number" in indexable_paths
    
    # 验证结构路径不在可索引路径中
    assert "address" not in indexable_paths
    assert "friends" not in indexable_paths
    assert "address.location" not in indexable_paths

def test_path_type_validation(manager):
    """测试路径类型验证"""
    class Item(BaseModel):
        tags: List[Dict[str, str]]  # 复合类型的列表
    
    with pytest.raises(PathValidationError) as exc_info:
        manager.register_object(
            Item,
            path_configs={
                "tags": {
                    "is_tag_list": True  # 不能将复合类型的列表标记为标签列表
                }
            }
        )
    assert "元素类型必须是字符串" in str(exc_info.value)

def test_value_extraction_for_indexing(manager):
    """测试用于索引的值提取"""
    class User(BaseModel):
        name: str
        age: int
        tags: List[str]
        profile: Dict[str, Any]
    
    user = User(
        name="test",
        age=25,
        tags=["tag1", "tag2"],
        profile={"type": "premium"}
    )
    
    manager.register_object(user, namespace="TestUser")
    
    # 提取可索引值
    name_value, _ = manager.extract_and_convert_value(user, "name", namespace="TestUser")
    assert name_value == "test"
    
    # 提取标签列表
    tags_value, _ = manager.extract_and_convert_value(user, "tags", namespace="TestUser")
    assert isinstance(tags_value, list)
    assert tags_value == ["tag1", "tag2"]
    
    # 提取结构类型应该引发错误
    with pytest.raises(PathTypeError) as exc_info:
        manager.extract_and_convert_value(user, "profile", namespace="TestUser")
    assert "期望类型为 indexable，实际类型为 structural" in str(exc_info.value)

def test_namespace_management(manager):
    """测试命名空间管理"""
    class User(BaseModel):
        name: str
        age: int

    # 测试自动命名空间
    manager.register_object(User)
    assert "User" in manager._path_types
    
    # 测试重复注册
    with pytest.raises(ValueError) as exc_info:
        manager.register_object(User)
    assert "命名空间 'User' 已存在" in str(exc_info.value)
    
    # 测试注销后重新注册
    manager.unregister_namespace("User")
    assert "User" not in manager._path_types
    
    # 重新注册应该成功
    manager.register_object(User)
    assert "User" in manager._path_types
    
    # 测试显式命名空间
    manager.register_object(User, namespace="CustomUser")
    assert "CustomUser" in manager._path_types
    
    # 测试注销不存在的命名空间
    with pytest.raises(KeyError) as exc_info:
        manager.unregister_namespace("NonExistent")
    assert "命名空间 'NonExistent' 不存在" in str(exc_info.value)

def test_list_str_path_registration(manager):
    """测试 List[str] 类型的路径注册和访问"""
    class TagContainer(BaseModel):
        tags: List[str]
        
    container = TagContainer(tags=["tag1", "tag2"])
    manager.register_object(container, namespace="TagContainer")
    
    # 测试整个列表的访问
    tags_value, path_info = manager.extract_and_convert_value(container, "tags", namespace="TagContainer")
    logger.info("提取的标签列表: value=%s, type=%s, path_info=%s", 
                tags_value, type(tags_value), 
                {'type_name': path_info.type_name, 'path_type': path_info.path_type})
    assert isinstance(tags_value, list)
    assert tags_value == ["tag1", "tag2"]
    
    # 测试单个元素的访问
    tag_value, path_info = manager.extract_and_convert_value(container, "tags[0]", namespace="TagContainer")
    logger.info("提取的单个标签: value=%s, type=%s, path_info=%s", 
                tag_value, type(tag_value),
                {'type_name': path_info.type_name, 'path_type': path_info.path_type})
    assert isinstance(tag_value, str)
    assert tag_value == "tag1"

def test_list_type_handling(manager):
    """测试各种列表类型的处理"""
    class ComplexContainer(BaseModel):
        # 基本列表类型
        str_list: List[str]
        int_list: List[int]
        float_list: List[float]
        
        # 空列表
        empty_list: List[str] = []
        
        # 嵌套列表
        nested_list: List[List[int]]
        
        # 带默认值的列表
        default_list: List[str] = ["default"]
        
        # 标签列表
        tags: List[str]
        
        # 可选列表
        optional_list: Optional[List[str]] = None

    container = ComplexContainer(
        str_list=["a", "b", "c"],
        int_list=[1, 2, 3],
        float_list=[1.1, 2.2, 3.3],
        nested_list=[[1, 2], [3, 4]],
        tags=["tag1", "tag2", "tag3"],
        optional_list=None
    )
    
    manager.register_object(container, namespace="ComplexContainer", path_configs={
        "tags": {"is_tag_list": True, "max_tags": 2}
    })
    
    # 测试基本列表访问
    str_list, info = manager.extract_and_convert_value(container, "str_list", namespace="ComplexContainer")
    assert isinstance(str_list, list)
    assert info.type_name == "List[str]"
    
    # 测试列表元素访问
    str_item, info = manager.extract_and_convert_value(container, "str_list[0]", namespace="ComplexContainer")
    assert isinstance(str_item, str)
    assert info.type_name == "str"
    
    # 测试空列表
    empty_list, info = manager.extract_and_convert_value(container, "empty_list", namespace="ComplexContainer")
    assert empty_list == []
    assert info.type_name == "List[str]"
    
    # 测试嵌套列表
    nested_list, info = manager.extract_and_convert_value(container, "nested_list[0]", namespace="ComplexContainer")
    assert isinstance(nested_list, list)
    assert info.type_name == "List[int]"
    
    # 测试标签列表截断
    tags, info = manager.extract_and_convert_value(container, "tags", namespace="ComplexContainer")
    assert len(tags) == 2
    assert tags == ["tag1", "tag2"]
    
    # 测试可选列表
    optional_list, info = manager.extract_and_convert_value(container, "optional_list", namespace="ComplexContainer")
    assert optional_list is None

def test_invalid_list_access(manager):
    """测试无效的列表访问"""
    class ListContainer(BaseModel):
        items: List[str]
    
    container = ListContainer(items=["a", "b", "c"])
    manager.register_object(container, namespace="ListContainer")
    
    # 测试越界访问
    with pytest.raises(PathValidationError):
        manager.extract_and_convert_value(container, "items[10]", namespace="ListContainer")
    
    # 测试无效索引
    with pytest.raises(PathValidationError):
        manager.extract_and_convert_value(container, "items[abc]", namespace="ListContainer")
    
    # 测试多重索引
    with pytest.raises(PathValidationError):
        manager.extract_and_convert_value(container, "items[0][1]", namespace="ListContainer")

def test_nested_structure_handling(manager):
    """测试嵌套结构的处理"""
    class Inner(BaseModel):
        value: str
        numbers: List[int]
    
    class Outer(BaseModel):
        name: str
        inner: Inner
        inner_list: List[Inner]
    
    inner = Inner(value="test", numbers=[1, 2, 3])
    outer = Outer(
        name="outer",
        inner=inner,
        inner_list=[
            Inner(value="one", numbers=[1]),
            Inner(value="two", numbers=[2])
        ]
    )
    
    manager.register_object(outer, namespace="Nested")
    
    # 测试嵌套对象访问
    inner_value, info = manager.extract_and_convert_value(outer, "inner.value", namespace="Nested")
    assert inner_value == "test"
    assert info.type_name == "str"
    
    # 测试嵌套列表访问
    inner_list_value, info = manager.extract_and_convert_value(outer, "inner_list[0].value", namespace="Nested")
    assert inner_list_value == "one"
    assert info.type_name == "str"
    
    # 测试嵌套列表中的列表访问
    numbers, info = manager.extract_and_convert_value(outer, "inner_list[1].numbers", namespace="Nested")
    assert numbers == [2]
    assert info.type_name == "List[int]"

def test_deeply_nested_list_types(manager):
    """测试深层嵌套的列表类型"""
    class DeepListContainer(BaseModel):
        # 基本列表
        simple_list: List[str]
        
        # 二层嵌套
        nested_list: List[List[int]]
        
        # 三层嵌套
        deep_list: List[List[List[str]]]
        
        # 混合嵌套
        mixed_list: List[List[List[int]]]
        
        # 带默认值的嵌套列表
        default_nested: List[List[str]] = [["a", "b"], ["c", "d"]]

    container = DeepListContainer(
        simple_list=["a", "b", "c"],
        nested_list=[[1, 2], [3, 4]],
        deep_list=[[["a", "b"], ["c"]], [["d"]], []],
        mixed_list=[[[1, 2]], [[3, 4], [5, 6]], []]
    )
    
    manager.register_object(container, namespace="deep")
    
    # 测试类型名称
    simple_list, info = manager.extract_and_convert_value(container, "simple_list", namespace="deep")
    assert info.type_name == "List[str]"
    
    nested_list, info = manager.extract_and_convert_value(container, "nested_list", namespace="deep")
    assert info.type_name == "List[List[int]]"
    
    deep_list, info = manager.extract_and_convert_value(container, "deep_list", namespace="deep")
    assert info.type_name == "List[List[List[str]]]"
    
    # 测试列表元素访问
    nested_element, info = manager.extract_and_convert_value(container, "nested_list[0]", namespace="deep")
    assert info.type_name == "List[int]"
    assert nested_element == [1, 2]
    
    deep_element, info = manager.extract_and_convert_value(container, "deep_list[0][0]", namespace="deep")
    assert info.type_name == "List[str]"
    assert deep_element == ["a", "b"]
    
    deepest_element, info = manager.extract_and_convert_value(container, "deep_list[0][0][0]", namespace="deep")
    assert info.type_name == "str"
    assert deepest_element == "a"
    
    # 测试空列表
    empty_list, info = manager.extract_and_convert_value(container, "deep_list[2]", namespace="deep")
    assert info.type_name == "List[List[str]]"
    assert empty_list == []
    
    # 测试带默认值的嵌套列表
    default_nested, info = manager.extract_and_convert_value(container, "default_nested", namespace="deep")
    assert info.type_name == "List[List[str]]"
    assert default_nested == [["a", "b"], ["c", "d"]]