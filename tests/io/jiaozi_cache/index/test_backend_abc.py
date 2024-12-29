import os
import pytest

from datetime import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Callable, Optional
from unittest import mock
from illufly.io.jiaozi_cache.index import IndexBackend, IndexConfig, Indexable
from pydantic import BaseModel, ConfigDict

@dataclass
class IndexableObject:
    """测试用的可索引对象"""
    value: Any
    
    def to_index_key(self) -> str:
        return f"custom_{self.value}"

class CustomType:
    """测试用的自定义类型
    
    用于测试自定义类型的转换支持。通过 from_string 类方法支持从字符串转换。
    """
    def __init__(self, value: str):
        self.value = value
    
    @classmethod
    def from_string(cls, value: str) -> 'CustomType':
        return cls(value)

class Address(BaseModel):
    """地址模型"""
    street: str
    city: str
    
    model_config = ConfigDict(
        frozen=True,
        validate_assignment=True,
        extra='forbid',
        str_strip_whitespace=True
    )
    
    def to_index_key(self) -> str:
        return f"{self.city}_{self.street}"

class User(BaseModel):
    """用户模型"""
    name: str
    age: int
    address: Optional[Address] = None
    tags: List[str] = []
    
    model_config = ConfigDict(
        validate_assignment=True,
        extra='forbid',
        str_strip_whitespace=True
    )

class TestIndexBackend(IndexBackend):
    """测试用的索引后端实现
    
    提供一个简单的基于内存的索引实现,用于测试 IndexBackend 的核心功能。
    使用字典存储数据,支持基本的增删改查操作。
    """
    def __init__(self, field_types: Dict[str, Any] = None, config: IndexConfig = None):
        super().__init__(field_types=field_types, config=config)
        self._data = {}  # 用于测试的简单存储

    def find_with_index(self, field: str, value: Any) -> List[str]:
        """使用索引查找"""
        self._update_stats("queries")
        result = []
        
        # 先转换查询值
        query_value, error = self.prepare_query_value(field, value)
        if error:
            self.logger.warning(f"查询值验证失败: {error}")
            return []
            
        for owner_id, data in self._data.items():
            # 提取被索引的值
            indexed_value, _ = self.extract_and_convert_value(data, field)
            if indexed_value is None:
                continue
                
            # 如果是 Pydantic 模型，转换为字典进行比较
            if isinstance(query_value, BaseModel):
                query_dict = query_value.model_dump()
                if isinstance(indexed_value, dict) and indexed_value == query_dict:
                    result.append(owner_id)
            # 否则直接比较值
            elif indexed_value == query_value:
                result.append(owner_id)
                
        return result

    def update_index(self, data: Any, owner_id: str) -> None:
        """更新索引"""
        self._update_stats("updates")
        self._data[owner_id] = data

    def remove_from_index(self, owner_id: str) -> None:
        """从索引中移除"""
        if owner_id in self._data:
            del self._data[owner_id]

    def has_index(self, field: str) -> bool:
        """检查字段是否已建立索引"""
        return field in self._field_types
    
    def rebuild_indexes(self, data_iterator: Callable[[], List[tuple[str, Any]]]) -> None:
        """重建所有索引数据"""
        pass

    def get_index_size(self) -> int:
        """获取索引大小"""
        return len(self._data)

    def get_index_memory_usage(self) -> int:
        """获取索引内存使用量（字节）"""
        return sum(len(str(data).encode()) for data in self._data.values())

class TestFieldPathValidation:
    """字段路径验证测试
    
    测试字段路径格式的验证功能,包括:
    - 简单字段路径
    - 嵌套字段路径
    - 数组索引路径
    - 多级嵌套路径
    - 无效路径格式
    """
    
    @pytest.mark.parametrize("field_types", [
        {"simple": str},
        {"nested.field": int},
        {"array[0]": str},
        {"deep.nested[0].field": bool},
        {"multiple.arrays[0][1]": list},
    ])
    def test_valid_field_paths(self, field_types):
        """测试有效的字段路径格式"""
        backend = TestIndexBackend(field_types=field_types)
        assert backend._field_types == field_types

    @pytest.mark.parametrize("field_types", [
        {"invalid[": str},
        {"missing]": int},
        {"invalid[a]": bool},
        {"double..dot": str},
        {"[0]invalid": list},
    ])
    def test_invalid_field_paths(self, field_types):
        """测试无效的字段路径格式"""
        with pytest.raises(ValueError):
            TestIndexBackend(field_types=field_types)

class TestPrepareQueryValue:
    """查询值准备和转换测试
    
    测试不同类型的查询值转换功能,包括:
    - 基本类型转换(str, int, float等)
    - 复杂类型转换(datetime, Decimal等)
    - 自定义类型转换
    - 多类型支持
    - 空值处理
    """
    
    @pytest.fixture
    def backend(self):
        field_types = {
            "str_field": str,
            "int_field": int,
            "float_field": float,
            "decimal_field": Decimal,
            "bool_field": bool,
            "datetime_field": datetime,
            "list_field": list,
            "custom_field": CustomType,
            "any_field": Any,
        }
        return TestIndexBackend(field_types=field_types)

    @pytest.mark.parametrize("field,value,expected", [
        ("int_field", "123", 123),
        ("float_field", "123.45", 123.45),
        ("decimal_field", "123.45", Decimal("123.45")),
        ("bool_field", "true", True),
        ("bool_field", "yes", True),
        ("bool_field", "1", True),
        ("bool_field", "false", False),
        ("datetime_field", "2024-01-01", datetime(2024, 1, 1)),
        ("datetime_field", "2024/01/01", datetime(2024, 1, 1)),
        ("str_field", 123, "123"),
    ])
    def test_successful_conversions(self, backend, field, value, expected):
        """测试成功的类型转换场景"""
        result, error = backend.prepare_query_value(field, value)
        assert error is None
        assert result == expected

    @pytest.mark.parametrize("field,value,error_expected", [
        ("int_field", "abc", True),
        ("float_field", "abc", True),
        ("bool_field", "invalid", True),
        ("datetime_field", "invalid", True),
        ("decimal_field", "abc", True),
    ])
    def test_failed_conversions(self, backend, field, value, error_expected):
        """测试失败的类型转换场景"""
        result, error = backend.prepare_query_value(field, value)
        assert result is None
        assert bool(error) == error_expected

    def test_none_value_handling(self, backend):
        """测试空值处理"""
        result, error = backend.prepare_query_value("any_field", None)
        assert result is None
        assert error is None

class TestExtractAndConvert:
    """值提取和转换测试
    
    测试从复杂数据结构中提取和转换值的功能,包括:
    - 简单字段提取
    - 嵌套字段提取
    - 数组索引提取
    - 深层嵌套提取
    - 错误处理
    """
    
    @pytest.fixture
    def backend(self):
        field_types = {
            "name": str,
            "age": int,
            "profile.email": str,
            "settings.theme.color": str,
            "tags[0]": str,
            "posts[0].title": str,
            "deep.nested[0].field[1]": str,
        }
        return TestIndexBackend(field_types=field_types)

    @pytest.mark.parametrize("data,field_path,expected_value", [
        (
            {"name": "test"},
            "name",
            "test"
        ),
        (
            {"profile": {"email": "test@example.com"}},
            "profile.email",
            "test@example.com"
        ),
        (
            {"tags": ["tag1", "tag2"]},
            "tags[0]",
            "tag1"
        ),
        (
            {"posts": [{"title": "Post 1"}]},
            "posts[0].title",
            "Post 1"
        ),
        (
            {"deep": {"nested": [{"field": ["v1", "v2"]}]}},
            "deep.nested[0].field[1]",
            "v2"
        ),
    ])
    def test_successful_extraction(self, backend, data, field_path, expected_value):
        """测试成功的值提取场景"""
        value, path = backend.extract_and_convert_value(data, field_path)
        assert value is not None
        assert isinstance(path, list)

    @pytest.mark.parametrize("data,field_path", [
        ({}, "nonexistent"),
        ({"profile": {}}, "profile.nonexistent"),
        ({"tags": []}, "tags[0]"),
        ({"deep": {"nested": []}}, "deep.nested[0].field"),
    ])
    def test_failed_extraction(self, backend, data, field_path):
        """测试失败的值提取场景"""
        value, path = backend.extract_and_convert_value(data, field_path)
        assert value is None
        assert isinstance(path, list)

    def test_nested_depth_limit(self, backend):
        """测试嵌套深度限制"""
        test_data = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": {
                            "value": "test"  # 简单类型作为索引值
                        }
                    }
                }
            }
        }
        
        # 测试有效路径 - 应该能够访问到简单类型的值
        valid_path = "level1.level2.level3.level4.value"
        value, path = backend.extract_and_convert_value(test_data, valid_path)
        assert value == "test"  # 验证能够获取到简单类型的值
        
        # 测试超出深度限制的路径
        invalid_path = "level1.level2.level3.level4.level5.value"
        value, path = backend.extract_and_convert_value(test_data, invalid_path)
        assert value is None  # 验证超出深度限制返回 None

    def test_indexable_object(self, backend):
        """测试可索引对象的处理"""
        data = {"obj": IndexableObject("test")}
        value, path = backend.extract_and_convert_value(data, "obj")
        assert value == "custom_test"

class TestPydanticSupport:
    """Pydantic 支持测试"""
    
    @pytest.fixture
    def backend(self):
        field_types = {
            ".": User,          # 整个对象的类型约束
            "name": str,        # 基本类型字段
            "age": int,
            "address": Address, # 复杂类型需实现 Indexable
            "tags": List[str],  # 标签列表类型
            "dict_tags": List[str]  # 添加字典标签字段的类型定义
        }
        return TestIndexBackend(field_types=field_types)

    def test_pydantic_model_extraction(self, backend):
        """测试 Pydantic 模型值提取"""
        user = User(
            name="Alice",
            age=25,
            address=Address(street="123 Main St", city="Boston"),
            tags=["tag1", "tag2"]
        )
        
        # 测试基本类型字段
        value, path = backend.extract_and_convert_value(user, "name")
        assert value == "Alice"
        
        value, path = backend.extract_and_convert_value(user, "age")
        assert value == 25
        
        # 测试复杂类型的值提取
        value, path = backend.extract_and_convert_value(user, "address")
        expected_key = user.address.to_index_key()
        assert value == expected_key
        
        # 测试标签列表 - 每个标签都是独立的索引值
        value, path = backend.extract_and_convert_value(user, "tags")
        assert isinstance(value, list)
        assert set(value) == {"tag1", "tag2"}

    def test_pydantic_value_conversion(self, backend):
        """测试 Pydantic 值转换"""
        # 测试基本类型转换
        value, error = backend.prepare_query_value("name", "Alice")
        assert error is None
        assert value == "Alice"
        
        # 测试复杂类型转换
        address = Address(street="123 Main St", city="Boston")
        value, error = backend.prepare_query_value("address", address)
        assert error is None
        assert value == address.to_index_key()
        
        # 测试根对象转换
        user = User(
            name="Alice",
            age=25,
            address=address
        )
        value, error = backend.prepare_query_value(".", user)
        assert error is None
        assert isinstance(value, User)

    def test_invalid_types(self, backend):
        """测试无效类型处理"""
        # 未实现 Indexable 的复杂类型
        complex_data = {
            "dict_field": {"key": "value"},
            "mixed_list": [1, "string", True]
        }
        
        value, path = backend.extract_and_convert_value(complex_data, "dict_field")
        assert value is None  # 应该拒绝处理未实现 Indexable 的字典
        
        value, path = backend.extract_and_convert_value(complex_data, "mixed_list")
        assert value is None  # 应该拒绝处理类型不一致的列表

    def test_indexable_object(self, backend):
        """测试可索引对象"""
        obj = IndexableObject(value="test")
        value, path = backend.extract_and_convert_value(obj, ".")
        assert value == obj  # 应该返回原对象，让 convert_to_index_key 处理

    def test_tag_limit(self, backend):
        """测试标签数量限制"""
        # 生成超过限制的标签列表
        many_tags = [f"tag{i}" for i in range(30)]  # 30 > 默认限制 20
        
        # Pydantic 模型标签
        user = User(
            name="Alice",
            age=25,
            tags=many_tags
        )
        values, path = backend.extract_and_convert_value(user, "tags")
        assert isinstance(values, list)
        assert len(values) == backend.MAX_TAGS
        assert values == many_tags[:backend.MAX_TAGS]
        
        # 字典标签
        data = {
            "dict_tags": many_tags
        }
        values, path = backend.extract_and_convert_value(data, "dict_tags")
        assert isinstance(values, list)
        assert len(values) == backend.MAX_TAGS
        assert values == many_tags[:backend.MAX_TAGS]
        
        # 测试环境变量配置
        with mock.patch.dict(os.environ, {'JIAOZI_INDEX_FIELD_MAX_TAGS': '5'}):
            backend_with_limit = TestIndexBackend(field_types={
                "tags": List[str],
                "dict_tags": List[str]  # 添加 dict_tags 字段类型
            })
            assert backend_with_limit.MAX_TAGS == 5
            
            values, path = backend_with_limit.extract_and_convert_value(data, "dict_tags")
            assert len(values) == 5
            assert values == many_tags[:5]

@dataclass
class TaggedObject:
    """带标签的可索引对象"""
    id: str
    tags: List[str]
    
    def to_index_key(self) -> str:
        return f"obj_{self.id}"

class TestTagSupport:
    """标签支持测试"""
    
    @pytest.fixture
    def backend(self):
        field_types = {
            "tags": List[str],           # Pydantic 模型标签字段
            "dict_tags": List[str],      # 字典标签字段
            "obj_tags": List[str],       # 对象标签字段
            "nested.tags": List[str]     # 嵌套标签字段
        }
        return TestIndexBackend(field_types=field_types)

    def test_tag_value_extraction(self, backend):
        """测试标签值提取 - 应该将标签列表转换为多个独立的索引值"""
        # Pydantic 模型标签
        user = User(
            name="Alice",
            age=25,  # 添加必填字段
            tags=["python", "web", "api"]
        )
        values, path = backend.extract_and_convert_value(user, "tags")
        assert isinstance(values, list)
        assert set(values) == {"python", "web", "api"}
        
        # 字典标签
        data = {
            "dict_tags": ["db", "cache", "redis"]
        }
        values, path = backend.extract_and_convert_value(data, "dict_tags")
        assert isinstance(values, list)
        assert set(values) == {"db", "cache", "redis"}
        
        # 嵌套标签
        nested = {
            "nested": {
                "tags": ["v1", "v2", "v3"]
            }
        }
        values, path = backend.extract_and_convert_value(nested, "nested.tags")
        assert isinstance(values, list)
        assert set(values) == {"v1", "v2", "v3"}

    def test_invalid_tag_values(self, backend):
        """测试无效的标签值 - 应该拒绝非字符串标签"""
        invalid_cases = [
            ["str", 123],        # 混合类型
            ["str", True],       # 包含布尔值
            [1, 2, 3],          # 全数字
            ["", "  ", None],   # 空值或空白
            []                  # 空列表
        ]
        
        for tags in invalid_cases:
            data = {"dict_tags": tags}
            values, path = backend.extract_and_convert_value(data, "dict_tags")
            assert values is None, f"应该拒绝无效的标签列表: {tags}"

    def test_tag_value_preparation(self, backend):
        """测试标签查询值准备 - 应该只接受单个字符串值"""
        # 有效的标签查询值
        value, error = backend.prepare_query_value("tags", "python")
        assert error is None
        assert value == "python"
        
        # 无效的查询值
        invalid_cases = [
            ["python", "web"],  # 列表不能用作查询值
            123,               # 非字符串
            "",               # 空字符串
            None,             # 空值
            True              # 布尔值
        ]
        
        for query in invalid_cases:
            value, error = backend.prepare_query_value("tags", query)
            assert error is not None, f"应该拒绝无效的标签查询值: {query}"
            assert value is None, f"无效的标签查询值应返回 None: {query}"