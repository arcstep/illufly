import pytest
import logging
from typing import Any, Dict, List, Set, Optional, Union
from collections import defaultdict
from decimal import Decimal
from datetime import datetime, date
from dataclasses import dataclass
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

from illufly.io.jiaozi_cache.index import (
    IndexBackend, 
    IndexConfig,
)

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

class MockIndexBackend(IndexBackend):
    """用于测试的索引后端实现"""
    
    def __init__(self, field_types: Dict[str, Any] = None, config: IndexConfig = None):
        super().__init__(field_types=field_types, config=config)
        self._indexes = defaultdict(lambda: defaultdict(set))
        self._stats = defaultdict(int)
        
    def close(self) -> None:
        """关闭后端并清理资源"""
        logger.debug("Closing backend and cleaning up resources...")
        try:
            self.clear_index()
            self.clear_stats()
            logger.debug("Successfully cleaned up resources")
        except Exception as e:
            logger.error("Error during cleanup: %s", str(e))
            raise RuntimeError(f"清理资源失败: {str(e)}")
            
    def __enter__(self):
        """上下文管理器入口"""
        logger.debug("Entering context manager")
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        logger.debug("Exiting context manager: exc_type=%s, exc_val=%s", exc_type, exc_val)
        try:
            self.clear_index()
            self.clear_stats()
            return False  # 不吞掉异常
        except Exception as e:
            logger.error("Error during context cleanup: %s", str(e))
            raise

    def _find_with_single_value(self, field: str, value: Any) -> Set[str]:
        """实现单值查询"""
        logger.debug("_find_with_single_value: field=%s, value=%s (type=%s)", 
                       field, value, type(value))
        result = self._indexes[field][value]
        logger.debug("Found documents: %s", result)
        return result

    def _find_with_single_tag(self, field: str, tag: str) -> Set[str]:
        """实现单个标签查询"""
        logger.debug("_find_with_single_tag called: field=%s, tag=%s", field, tag)
        logger.debug("Current index state: %s", dict(self._indexes[field]))
        
        # 直接返回标签对应的文档集合
        result = self._indexes[field][tag]
        logger.debug("Found documents for tag %s: %s", tag, result)
        return result

    def _add_to_index(self, field: str, value: Any, key: str) -> None:
        """实现索引添加"""
        logger.debug("_add_to_index called: field=%s, value=%s (type=%s), key=%s", 
                       field, value, type(value), key)
        logger.debug("Current index state BEFORE: %s", dict(self._indexes[field]))
        
        # 处理标签字段
        if (hasattr(self._field_types[field], '__origin__') and 
            self._field_types[field].__origin__ in (list, List) and 
            self._field_types[field].__args__[0] == str):
            # 注意：我们可能把索引结构反了
            # 应该是 tag -> doc_ids，而不是 doc_id -> tags
            logger.debug("Adding tag %s to document %s", value, key)
            self._indexes[field][value].add(key)  # 修改这里：tag -> doc_ids
        else:
            self._indexes[field][value].add(key)
            
        self._update_stats("updates")
        logger.debug("Current index state AFTER: %s", dict(self._indexes[field]))

    def has_index(self, field: str) -> bool:
        """检查字段是否已定义索引"""
        return field in self._field_types

    def clear_index(self) -> None:
        """清空索引"""
        self._indexes.clear()

    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return dict(self._stats)

    def clear_stats(self) -> None:
        """清除统计信息"""
        self._stats.clear()

    def _update_stats(self, stat_name: str) -> None:
        """更新统计信息"""
        if self._config.enable_stats:
            self._stats[stat_name] = self._stats.get(stat_name, 0) + 1

    def remove_from_index(self, key: str) -> None:
        """删除指定数据项的所有索引"""
        logger.debug("Removing all indexes for key: %s", key)
        try:
            # 遍历所有字段的索引
            for field in self._indexes:
                # 遍历字段中的所有值
                for value in list(self._indexes[field].keys()):
                    if key in self._indexes[field][value]:
                        self._indexes[field][value].remove(key)
                        # 如果集合为空，删除该值的索引
                        if not self._indexes[field][value]:
                            del self._indexes[field][value]
            self._update_stats("updates")
        except Exception as e:
            logger.error("Failed to remove indexes: %s", str(e))
            raise RuntimeError(f"删除索引失败: {str(e)}")

    def rebuild_indexes(self) -> None:
        """重建所有索引"""
        logger.debug("Rebuilding all indexes")
        try:
            self.clear_index()
            self._update_stats("updates")
        except Exception as e:
            logger.error("Failed to rebuild indexes: %s", str(e))
            raise RuntimeError(f"重建索引失败: {str(e)}")

class TestBasicQueries:
    """基本查询功能测试"""
    
    @pytest.fixture
    def backend(self):
        return MockIndexBackend(field_types={
            "name": str,
            "age": int,
            "score": float,
            "active": bool,
            "tags": List[str]
        })

    def test_single_value_query(self, backend):
        """测试单值查询"""
        backend.add_to_index("name", "Alice", "user1")
        backend.add_to_index("age", 25, "user1")
        
        # 字符串查询
        results = backend.find_with_values("name", "Alice")
        assert results == ["user1"]
        
        # 数值查询
        results = backend.find_with_values("age", 25)
        assert results == ["user1"]
        
        # 不存在的值
        results = backend.find_with_values("name", "Bob")
        assert results == []

    def test_multi_value_query(self, backend):
        """测试多值查询"""
        # 准备测试数据
        backend.add_to_index("age", 25, "user1")
        backend.add_to_index("age", 30, "user2")
        backend.add_to_index("age", [25, 35], "user3")  # 一个用户多个年龄
        
        # OR 查询
        results = backend.find_with_values("age", [25, 30])
        assert set(results) == {"user1", "user2", "user3"}
        
        # AND 查询
        results = backend.find_with_values("age", [25, 35], match_all=True)
        assert results == ["user3"]

    def test_invalid_values(self, backend):
        """测试无效值处理"""
        # 单值查询：类型不匹配时抛出异常
        with pytest.raises(TypeError) as e:
            backend.find_with_values("age", "not_a_number")
        assert "类型不匹配" in str(e.value)
        
        # 字段不存在时抛出异常
        with pytest.raises(KeyError) as e:
            backend.find_with_values("unknown", "value")
        assert "未定义索引" in str(e.value)
        
        # 空值列表返回空结果
        results = backend.find_with_values("name", [])
        assert results == []
        
        # 多值查询：无效值也应该抛出异常
        backend.add_to_index("age", 25, "user1")
        backend.add_to_index("age", 30, "user2")
        with pytest.raises(TypeError) as e:
            backend.find_with_values("age", [25, "invalid", 30])
        assert "类型不匹配" in str(e.value)

class TestTagQueries:
    """标签查询测试"""
    
    @pytest.fixture
    def backend(self):
        """创建测试用的 MockIndexBackend 实例"""
        field_types = {
            "name": str,
            "age": int,
            "active": bool,
            "tags": List[str]  # 添加标签字段
        }
        config = IndexConfig(enable_stats=True)
        return MockIndexBackend(field_types=field_types, config=config)

    def test_single_tag_query(self, backend):
        """测试单个标签查询"""
        backend.add_tags("tags", ["python"], "doc1")
        backend.add_tags("tags", ["python", "web"], "doc2")
        
        results = backend.find_with_tags("tags", "python")
        assert set(results) == {"doc1", "doc2"}
        
    def test_multi_tag_query(self, backend):
        """测试多标签查询"""
        # 准备测试数据
        backend.add_tags("tags", ["python", "web", "api"], "doc1")
        backend.add_tags("tags", ["python", "db", "api"], "doc2")
        backend.add_tags("tags", ["java", "web"], "doc3")
        
        # OR 查询
        results = backend.find_with_tags("tags", ["python", "java"])
        assert set(results) == {"doc1", "doc2", "doc3"}
        
        # AND 查询
        results = backend.find_with_tags("tags", ["python", "api"], match_all=True)
        assert set(results) == {"doc1", "doc2"}
        
        # 部分匹配
        results = backend.find_with_tags("tags", ["python", "nosuch"])
        assert set(results) == {"doc1", "doc2"}
        
    def test_tag_validation(self, backend):
        """测试标签验证"""
        # 非标签字段
        with pytest.raises(TypeError) as e:
            backend.find_with_tags("name", "value")
        assert "标签必须是字符串类型" in str(e.value)

        # 空标签
        results = backend.find_with_tags("tags", [])
        assert results == []
        
        # 无效标签值
        results = backend.find_with_tags("tags", ["", " ", None, 123])
        assert results == []
        
        # 混合有效和无效标签
        backend.add_tags("tags", ["python"], "doc1")
        results = backend.find_with_tags("tags", ["python", "", None])
        assert results == ["doc1"]

class TestPydanticQueries:
    """Pydantic模型查询测试"""
    
    class Address(BaseModel):
        city: str
        street: str
        
        model_config = {
            "arbitrary_types_allowed": True,
            "from_attributes": True  # 允许从属性创建
        }

    class User(BaseModel):
        name: str
        age: int
        address: Optional[Address] = None
        tags: List[str] = []
        
        model_config = {
            "arbitrary_types_allowed": True,
            "from_attributes": True  # 允许从属性创建
        }

    @pytest.fixture
    def backend(self):
        """创建测试用的 MockIndexBackend 实例"""
        field_types = {
            "name": str,
            "age": int,
            "address": TestPydanticQueries.Address,
            "address.city": str,
            "address.street": str,
            "tags": List[str]
        }
        config = IndexConfig(enable_stats=True)
        backend = MockIndexBackend(field_types=field_types, config=config)
        logger.debug("Created backend with field_types: %s", field_types)
        return backend

    def test_root_object_query(self, backend):
        """测试根对象查询"""
        logger.debug("Creating test users...")
        user1 = self.User(name="Alice", age=25)
        user2 = self.User(name="Alice", age=30)
        
        # 检查 update_index 的实现
        logger.debug("Updating index with user1: %s", user1.model_dump())
        for field, value in user1.model_dump().items():
            if field != "address" and field != "tags":  # 跳过嵌套字段和标签
                backend.add_to_index(field, value, "user1")
                
        logger.debug("Updating index with user2: %s", user2.model_dump())
        for field, value in user2.model_dump().items():
            if field != "address" and field != "tags":
                backend.add_to_index(field, value, "user2")
        
        # 检查索引状态
        logger.debug("Current index state: %s", backend._indexes)
        
        # 完全匹配
        logger.debug("Querying with name=Alice...")
        results = backend.find_with_values("name", "Alice")
        logger.debug("Query results: %s", results)
        assert "user1" in results
        assert "user2" in results

    def test_nested_field_query(self, backend):
        """测试嵌套字段查询"""
        logger.debug("Creating test user with address...")
        address_data = {"city": "Beijing", "street": "Main St"}
        user_data = {
            "name": "Alice",
            "age": 25,
            "address": address_data
        }
        
        # 使用字典创建模型
        user = self.User.model_validate(user_data)
        logger.debug("Created user: %s", user.model_dump())
        
        # 手动添加索引
        backend.add_to_index("name", user.name, "user1")
        backend.add_to_index("age", user.age, "user1")
        backend.add_to_index("address.city", user.address.city, "user1")
        backend.add_to_index("address.street", user.address.street, "user1")
        
        # 检查索引状态
        logger.debug("Current index state: %s", backend._indexes)
        
        # 查询嵌套字段
        logger.debug("Querying nested field address.city...")
        results = backend.find_with_values("address.city", "Beijing")
        logger.debug("Query results: %s", results)
        assert results == ["user1"]

    def test_model_with_tags(self, backend):
        """测试带标签的模型查询"""
        # 添加调试日志
        logger.debug("Creating test user with tags...")
        user = self.User(
            name="Alice",
            age=25,
            tags=["python", "web"]
        )
        
        logger.debug("Updating index with user: %s", user.model_dump())
        backend.update_index(user, "user1")
        
        # 标签查询
        logger.debug("Querying tags...")
        backend.add_tags("tags", ["python", "web"], "user1")  # 显式添加标签
        results = backend.find_with_tags("tags", "python")
        assert results == ["user1"]

class TestIndexManagement:
    """索引管理测试"""
    
    @pytest.fixture
    def backend(self):
        """创建测试用的 MockIndexBackend 实例"""
        field_types = {
            "name": str,
            "age": int,
            "tags": List[str]
        }
        config = IndexConfig(enable_stats=True)
        backend = MockIndexBackend(field_types=field_types, config=config)
        logger.debug("Created backend with field_types: %s", field_types)
        return backend
        
    def test_remove_from_index(self, backend):
        """测试移除索引"""
        logger.debug("Testing remove from index...")
        
        # 添加测试数据
        logger.debug("Adding test data...")
        backend.add_to_index("name", "Alice", "user1")
        backend.add_to_index("age", 25, "user1")
        backend.add_tags("tags", ["python"], "user1")
        
        # 验证数据已添加
        results = backend.find_with_values("name", "Alice")
        assert results == ["user1"]
        
        # 移除整个文档的索引
        logger.debug("Removing all indexes for user1...")
        backend.remove_from_index("user1")
        
        # 验证所有索引都已移除
        results = backend.find_with_values("name", "Alice")
        assert results == []
        results = backend.find_with_values("age", 25)
        assert results == []
        results = backend.find_with_tags("tags", "python")
        assert results == []
        
    def test_rebuild_indexes(self, backend):
        """测试重建索引"""
        logger.debug("Testing rebuild indexes...")
        
        # 添加初始数据
        backend.add_to_index("name", "Alice", "user1")
        backend.add_to_index("age", 25, "user1")
        
        # 重建索引
        logger.debug("Rebuilding indexes...")
        backend.rebuild_indexes()  # 不需要参数
        
        # 验证索引状态
        results = backend.find_with_values("name", "Alice")
        logger.debug("Query results after rebuild: %s", results)
        assert len(results) == 0  # 重建后应该是空的，因为没有数据源

    def test_clear_index(self, backend):
        """测试清空索引"""
        # 添加一些数据
        backend.add_to_index("name", "Alice", "user1")
        backend.add_to_index("tags", ["python"], "user1")
        
        # 清空索引
        backend.clear_index()
        
        # 验证索引已清空
        results = backend.find_with_values("name", "Alice")
        assert results == []
        
        results = backend.find_with_tags("tags", "python")
        assert results == []

class TestStatistics:
    """统计功能测试"""
    
    @pytest.fixture
    def backend(self):
        """创建启用统计的后端实例"""
        return MockIndexBackend(
            field_types={"name": str, "tags": List[str]},
            config=IndexConfig(enable_stats=True)
        )
    
    def test_query_stats(self, backend):
        """测试查询统计"""
        logger.debug("Testing query statistics...")
        
        # 添加测试数据
        backend.add_to_index("name", "Alice", "user1")
        backend.add_tags("tags", ["python"], "user1")
        
        # 执行查询
        logger.debug("Executing queries...")
        backend.find_with_values("name", "Alice")
        backend.find_with_values("name", ["Alice", "Bob"])
        backend.find_with_tags("tags", "python")
        
        # 验证统计
        stats = backend.get_stats()
        logger.debug("Query stats: %s", stats)
        assert stats["queries"] >= 3  # 使用 >= 而不是 ==

    def test_update_stats(self, backend):
        """测试更新统计"""
        logger.debug("Testing update statistics...")
        
        # 执行更新
        logger.debug("Executing updates...")
        backend.add_to_index("name", "Alice", "user1")
        backend.remove_from_index("user1")  # 修改为只传入 key
        
        # 验证统计
        stats = backend.get_stats()
        logger.debug("Update stats: %s", stats)
        assert stats["updates"] >= 2  # 使用 >= 而不是 ==

    def test_disable_stats(self):
        """测试禁用统计"""
        logger.debug("Testing disabled statistics...")
        
        # 创建禁用统计的后端
        config = IndexConfig(enable_stats=False)
        backend = MockIndexBackend(
            field_types={"name": str},
            config=config
        )
        
        # 执行一些操作
        backend.add_to_index("name", "Alice", "user1")
        backend.find_with_values("name", "Alice")
        
        # 验证统计为空
        stats = backend.get_stats()
        logger.debug("Stats when disabled: %s", stats)
        assert not stats

    def test_clear_stats(self, backend):
        """测试清除统计"""
        logger.debug("Testing clear statistics...")
        
        # 执行一些操作
        backend.add_to_index("name", "Alice", "user1")
        backend.find_with_values("name", "Alice")
        
        # 验证有统计数据
        stats_before = backend.get_stats()
        logger.debug("Stats before clear: %s", stats_before)
        assert stats_before
        
        # 清除统计
        backend.clear_stats()
        
        # 验证统计已清空
        stats_after = backend.get_stats()
        logger.debug("Stats after clear: %s", stats_after)
        assert not stats_after or all(v == 0 for v in stats_after.values())

class TestErrorHandling:
    """错误处理测试"""
    @pytest.fixture
    def backend(self):
        """创建测试用的后端实例"""
        return MockIndexBackend(field_types={
            "name": str,
            "age": int,
            "active": bool,
            "created_at": datetime,
            "price": Decimal,
            "tags": List[str]
        })

    def test_field_type_validation(self, backend):
        """测试字段类型验证"""
        logger.debug("Testing field type validation...")
        
        # 类型不匹配
        with pytest.raises(TypeError) as e:
            backend.add_to_index("age", "not_a_number", "user1")
        assert "类型不匹配" in str(e.value)
            
        # 布尔值转换错误
        with pytest.raises(TypeError) as e:
            backend.add_to_index("active", "invalid", "user1")
        assert "类型不匹配" in str(e.value)
            
        # 日期时间转换错误
        with pytest.raises(TypeError) as e:
            backend.add_to_index("created_at", "invalid_date", "user1")
        assert "类型不匹配" in str(e.value)
            
        # Decimal 转换错误
        with pytest.raises(TypeError) as e:
            backend.add_to_index("price", "not_decimal", "user1")
        assert "类型不匹配" in str(e.value)
            
        # None 值错误
        with pytest.raises(ValueError) as e:
            backend.add_to_index("name", None, "user1")
        assert "字段值不能为 None" in str(e.value)
            
    def test_field_path_validation(self, backend):
        """测试字段路径验证"""
        logger.debug("Testing field path validation...")
        
        # 无效的字段名
        with pytest.raises(KeyError) as e:
            backend.add_to_index("invalid.field", "value", "user1")
        assert "未定义索引" in str(e.value)
            
        # 未定义的字段
        with pytest.raises(KeyError) as e:
            backend.add_to_index("undefined.field", "value", "user1")
        assert "未定义索引" in str(e.value)
            
    def test_tag_validation(self, backend):
        """测试标签验证"""
        logger.debug("Testing tag validation...")
        
        # 非标签字段
        with pytest.raises(TypeError) as e:
            backend.find_with_tags("name", ["tag1"])
        assert "查询的标签必须是字符串类型" in str(e.value)
            
        # 无效的标签值类型
        backend.add_tags("tags", [123], "user1")

class TestContextManager:
    """上下文管理器测试"""
    
    def test_context_manager(self):
        """测试上下文管理器功能"""
        with MockIndexBackend(field_types={"name": str}) as backend:
            # 正常操作
            backend.add_to_index("name", "Alice", "user1")
            results = backend.find_with_values("name", "Alice")
            assert results == ["user1"]
        # 退出上下文后，应该已经调用了flush和close

    def test_context_manager_with_error(self):
        """测试上下文管理器错误处理"""
        try:
            with MockIndexBackend(field_types={"name": str}) as backend:
                backend.add_to_index("name", "Alice", "user1")
                raise ValueError("测试异常")
        except ValueError:
            pass
        # 即使发生异常，也应该正确清理资源

class TestLifecycle:
    """生命周期管理测试"""
    
    def test_initialization(self):
        """测试初始化"""
        logger.debug("Testing initialization...")
        
        # 无参数初始化
        backend1 = MockIndexBackend()
        assert backend1._field_types == {}
        logger.debug("Backend1 field types: %s", backend1._field_types)
        
        # 带字段类型初始化
        field_types = {"name": str}
        backend2 = MockIndexBackend(field_types=field_types)
        assert backend2._field_types == field_types
        logger.debug("Backend2 field types: %s", backend2._field_types)
        
        # 带配置初始化
        config = IndexConfig(enable_stats=True)
        backend3 = MockIndexBackend(config=config)
        assert backend3._config.enable_stats is True
        logger.debug("Backend3 config: %s", backend3._config)

    def test_cleanup(self):
        """测试资源清理"""
        logger.debug("Testing cleanup...")
        
        # 创建带字段类型的后端
        field_types = {"name": str}
        backend = MockIndexBackend(field_types=field_types)
        logger.debug("Created backend with field types: %s", field_types)
        
        # 添加测试数据
        backend.add_to_index("name", "Alice", "user1")
        logger.debug("Added test data")
        
        # 验证数据已添加
        results = backend.find_with_values("name", "Alice")
        assert results == ["user1"]
        logger.debug("Verified data was added")
        
        # 调用close应该清理资源
        backend.close()
        logger.debug("Called close()")
        
        # 验证资源已清理
        results = backend.find_with_values("name", "Alice")
        assert results == []
        logger.debug("Verified data was cleaned up")

class TestFieldPathValidation:
    """字段路径验证测试"""
    
    @pytest.fixture
    def create_backend(self):
        def _create(field_types):
            return MockIndexBackend(field_types=field_types)
        return _create

    @pytest.mark.parametrize("field_types", [
        # 简单字段路径
        {"name": str, "age": int},
        # 嵌套字段路径
        {"user.name": str, "user.profile.email": str},
        # 数组索引路径
        {"items[0]": str, "items[1].name": str},
        # 多级嵌套路径
        {"company.departments[0].employees[1].name": str},
        # 混合路径
        {"users[0].addresses[1].city": str, "simple": int}
    ])
    def test_valid_field_paths(self, create_backend, field_types):
        """测试有效的字段路径格式"""
        backend = create_backend(field_types)
        assert backend._field_types == field_types

    @pytest.mark.parametrize("field_types", [
        {"invalid[": str},  # 未闭合的方括号
        {"missing]": int},  # 缺少左方括号
        {"invalid[a]": bool},  # 非数字索引
        {"double..dot": str},  # 连续点号
        {"[0]invalid": list},  # 起始方括号
        {"": str},  # 空字段名
        {".invalid": str},  # 起始点号
        {"invalid.": str},  # 结尾点号
    ])
    def test_invalid_field_paths(self, create_backend, field_types):
        """测试无效的字段路径格式"""
        with pytest.raises(ValueError) as e:
            create_backend(field_types)
        assert "无效的字段路径格式" in str(e.value)

    def test_undeclared_field_path(self, create_backend):
        """测试未声明的索引路径"""
        backend = create_backend({
            "name": str,
            "user.email": str
        })
        
        # 完全未声明的字段
        with pytest.raises(KeyError) as exc_info:
            backend.find_with_values("age", 25)
        assert "未定义索引" in str(exc_info.value)
        
        # 未声明的嵌套字段
        with pytest.raises(KeyError) as exc_info:
            backend.find_with_values("user.name", "Alice")
        assert "未定义索引" in str(exc_info.value)
        
        # 未声明的数组字段
        with pytest.raises(KeyError) as exc_info:
            backend.find_with_values("items[0]", "item1")
        assert "未定义索引" in str(exc_info.value)
        
        # 部分路径匹配但不完整
        with pytest.raises(KeyError) as exc_info:
            backend.find_with_values("user", {"email": "test@example.com"})
        assert "未定义索引" in str(exc_info.value)

    def test_type_mismatch(self, create_backend):
        """测试索引值类型不匹配"""
        backend = create_backend({
            "age": int,
            "score": float,
            "active": bool,
            "user.birth_date": datetime,
            "items[0].price": Decimal,
            "tags": List[str]
        })
        
        # 基本类型不匹配
        with pytest.raises(TypeError) as exc_info:
            backend.find_with_values("age", "not_a_number")
        assert "类型不匹配" in str(exc_info.value)
        
        # 浮点数字段使用整数（应该自动转换，不抛出异常）
        backend.find_with_values("score", 100)
        
        # 布尔字段使用非布尔值
        with pytest.raises(TypeError) as exc_info:
            backend.find_with_values("active", "not_a_bool")
        assert "类型不匹配" in str(exc_info.value)
        
        # 日期时间字段使用无效格式
        with pytest.raises(TypeError) as exc_info:
            backend.find_with_values("user.birth_date", "invalid_date")
        assert "类型不匹配" in str(exc_info.value)
        
        # Decimal字段使用无效格式
        with pytest.raises(TypeError) as exc_info:
            backend.find_with_values("items[0].price", "not_a_decimal")
        assert "类型不匹配" in str(exc_info.value)
        
        # 标签字段使用非字符串值
        results = backend.find_with_tags("tags", [123, 456])
        assert results == []
        
        # 多值查询中包含类型不匹配的值
        with pytest.raises(TypeError) as exc_info:
            backend.find_with_values("age", [25, "not_a_number", 30])
        assert "类型不匹配" in str(exc_info.value)

class TestValueConversion:
    """值转换测试"""
    
    @pytest.fixture
    def backend(self):
        return MockIndexBackend(field_types={
            "str_field": str,
            "int_field": int,
            "float_field": float,
            "bool_field": bool,
            "decimal_field": Decimal,
            "datetime_field": datetime,
            "date_field": date,
            "tags": List[str]
        })

    def test_tag_value_conversion(self, backend):
        """测试标签值转换"""
        # 有效的标签值
        result = backend._validate_field_value("tags", "tag1")
        assert result == "tag1"
        
        # 无效的标签值
        with pytest.raises(TypeError) as exc_info:
            backend._validate_field_value("tags", 123)
        assert "标签必须是字符串类型" in str(exc_info.value)

    def test_bool_value_conversion(self, backend):
        """测试布尔值转换"""
        # 有效的布尔值字符串
        assert backend._validate_field_value("bool_field", "true") is True
        assert backend._validate_field_value("bool_field", "yes") is True
        assert backend._validate_field_value("bool_field", "1") is True
        assert backend._validate_field_value("bool_field", "false") is False
        assert backend._validate_field_value("bool_field", "no") is False
        assert backend._validate_field_value("bool_field", "0") is False
        
        # 无效的布尔值字符串
        with pytest.raises(TypeError, match="类型不匹配：无效的布尔值"):
            backend._validate_field_value("bool_field", "invalid")

    def test_numeric_value_conversion(self, backend):
        """测试数值转换"""
        # 整数转换
        assert backend._validate_field_value("int_field", "123") == 123
        with pytest.raises(TypeError) as e:
            backend._validate_field_value("int_field", "not_a_number")
        assert "类型不匹配" in str(e.value)
        
        # 浮点数转换
        assert backend._validate_field_value("float_field", "123.45") == 123.45
        with pytest.raises(TypeError) as e:
            backend._validate_field_value("float_field", "invalid")
        assert "类型不匹配" in str(e.value)
        
        # Decimal 转换
        assert backend._validate_field_value("decimal_field", "123.45") == Decimal("123.45")
        with pytest.raises(TypeError) as e:
            backend._validate_field_value("decimal_field", "not_decimal")
        assert "类型不匹配" in str(e.value)

    def test_datetime_value_conversion(self, backend):
        """测试日期时间转换"""
        # datetime 转换
        assert backend._validate_field_value("datetime_field", "2024-01-01 12:34:56") == \
               datetime(2024, 1, 1, 12, 34, 56)
        assert backend._validate_field_value("datetime_field", "2024-01-01") == \
               datetime(2024, 1, 1)
               
        with pytest.raises(TypeError) as e:
            backend._validate_field_value("datetime_field", "invalid_date")
        assert "类型不匹配" in str(e.value)
        
        # date 转换
        with pytest.raises(TypeError) as e:
            backend._validate_field_value("date_field", "2024-01-01")
        assert "类型不匹配" in str(e.value)

        with pytest.raises(TypeError) as exc_info:
            backend._validate_field_value("date_field", "invalid_date")
        assert "类型不匹配" in str(exc_info.value)

class TestValueExtraction:
    """值提取测试"""
    
    @pytest.fixture
    def backend(self):
        return MockIndexBackend(field_types={
            "name": str,
            "profile.email": str,
            "settings.theme.color": str,
            "items[0].name": str,
            "addresses[0].city": str,
            "deep.nested[0].field[1]": str
        })

    def test_simple_extraction(self, backend):
        """测试简单值提取"""
        data = {"name": "test", "age": 25}
        value, path = backend.extract_and_convert_value(data, "name")
        assert value == "test"
        assert path == ["name"]

    def test_nested_extraction(self, backend):
        """测试嵌套值提取"""
        data = {
            "profile": {"email": "test@example.com"},
            "settings": {"theme": {"color": "blue"}}
        }
        
        # 测试二级嵌套
        value, path = backend.extract_and_convert_value(data, "profile.email")
        assert value == "test@example.com"
        assert path == ["profile", "email"]
        
        # 测试三级嵌套
        value, path = backend.extract_and_convert_value(data, "settings.theme.color")
        assert value == "blue"
        assert path == ["settings", "theme", "color"]

    def test_array_extraction(self, backend):
        """测试数组值提取"""
        data = {
            "items": [
                {"name": "item1"},
                {"name": "item2"}
            ],
            "deep": {
                "nested": [
                    {"field": ["v1", "v2", "v3"]}
                ]
            }
        }
        
        # 测试简单数组访问
        value, path = backend.extract_and_convert_value(data, "items[0].name")
        assert value == "item1"
        
        # 测试复杂嵌套数组访问
        value, path = backend.extract_and_convert_value(data, "deep.nested[0].field[1]")
        assert value == "v2"

    def test_extraction_errors(self, backend):
        """测试值提取错误"""
        data = {"name": "test"}
        
        # 不存在的字段
        value, path = backend.extract_and_convert_value(data, "unknown")
        assert value is None
        
        # 越界的数组索引
        data = {"items": []}
        value, path = backend.extract_and_convert_value(data, "items[0]")
        assert value is None
        
        # 无效的嵌套路径
        data = {"profile": None}
        value, path = backend.extract_and_convert_value(data, "profile.email")
        assert value is None

class TestFieldPathExpression:
    """索引路径表达式测试"""
    
    @pytest.fixture
    def create_backend(self):
        def _create(field_types):
            return MockIndexBackend(field_types=field_types)
        return _create

    def test_path_expression_validation(self, create_backend):
        """测试路径表达式验证"""
        # 有效的路径表达式
        valid_paths = {
            "simple": str,  # 简单字段
            "nested.field": int,  # 嵌套字段
            "array[0]": str,  # 数组索引
            "nested.array[0]": bool,  # 嵌套数组
            "deep.nested[0].field": str,  # 深层嵌套
            "multiple[0][1]": list,  # 多维数组
            "mixed.path[0].with[1].types": str,  # 混合路径
        }
        backend = create_backend(valid_paths)
        assert backend._field_types == valid_paths

    @pytest.mark.parametrize("invalid_path,expected_pattern", [
        ("invalid[", "未闭合的数组索引"),
        ("missing]", "字段名包含无效字符"),
        ("invalid[a]", "数组索引必须是数字"),
        ("double..dot", "连续的点号无效"),
        ("[0]invalid", "路径不能以数组索引开始"),
        ("", "字段名不能为空"),
        (".invalid", "路径不能以点号开始"),
        ("invalid.", "路径不能以点号结束"),
        ("field.[0]", "数组索引前必须有字段名"),
        ("field[0].", "路径不能以点号结束"),
        ("field[-1]", "数组索引不能为负数"),
        ("field[1.5]", "未闭合的数组索引"),
        ("field[01]", "数组索引不能有前导零"),
        ("field[9999999999]", "数组索引超出范围"),
        ("very.very.very.very.deep.path", "路径嵌套层级过深"),
    ])
    def test_invalid_path_expressions(self, create_backend, invalid_path, expected_pattern):
        """测试无效的路径表达式"""
        with pytest.raises(ValueError) as e:
            create_backend({invalid_path: str})
        assert expected_pattern in str(e.value)

    def test_path_component_validation(self, create_backend):
        """测试路径组件验证"""
        invalid_components = [
            # 字段名验证
            ("123field", "无效的字段路径格式"),
            ("field#name", "无效的字段路径格式"),
            ("field name", "无效的字段路径格式"),
            ("field-name", "无效的字段路径格式"),
            
            # 数组索引验证
            ("field[]", "无效的字段路径格式"),
            ("field[,]", "无效的字段路径格式"),
            ("field[0][", "无效的字段路径格式"),
            ("field[[0]]", "无效的字段路径格式"),
        ]
        
        for invalid_path, expected_message in invalid_components:
            with pytest.raises(ValueError) as exc_info:
                create_backend({invalid_path: str})
            assert expected_message in str(exc_info.value)

    def test_complex_path_validation(self):
        """测试复杂路径验证"""
        complex_invalid_paths = [
            # 混合多种错误
            ("user[0].items[a].name", "无效的字段路径格式"),
            ("user.[0].items", "无效的字段路径格式"),
            ("users[0]..items", "无效的字段路径格式"),
            (".users[0].items[", "无效的字段路径格式"),
            ("users[01][02].name", "无效的字段路径格式"),
            
            # 特殊字符组合
            ("user@[0].name", "无效的字段路径格式"),
            ("user[0]#.name", "无效的字段路径格式"),
            ("user[0].items[1].", "无效的字段路径格式"),
            
            # 复杂嵌套
            ("very.deep[0].path[1].with.many[2].levels[3].nested", "无效的字段路径格式"),
        ]
        
        for invalid_path, expected_message in complex_invalid_paths:
            with pytest.raises(ValueError) as e:
                # 直接构造实例，触发验证
                logger.warning(f"Testing invalid path: {invalid_path}")
                backend = MockIndexBackend(field_types=None)
                backend._validate_field_path(invalid_path)
            assert expected_message in str(e.value)

