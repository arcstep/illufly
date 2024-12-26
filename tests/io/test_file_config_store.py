from dataclasses import dataclass
from typing import Callable
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass, field
from typing import Dict, Any

import pytest
import logging
import json
from unittest.mock import patch

from illufly.io import TinyFileDB
from pydantic import BaseModel, Field

@dataclass(frozen=True)
class StorageData:
    """测试用数据类"""
    id: str = "1"
    name: str = "张三"
    age: int = 25
    email: str = "test@example.com"
    
    def to_dict(self) -> dict:
        """序列化方法"""
        return {
            "id": self.id,
            "name": self.name,
            "age": self.age,
            "email": self.email
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'StorageData':
        """反序列化方法"""
        return cls(
            id=data["id"],
            name=data["name"],
            age=data["age"],
            email=data["email"]
        )

class TestSimpleStorageData:

    @pytest.fixture
    def test_data_factory(self, tmp_path):
        def create_test_data(**kwargs):
            defaults = {
                "id": "1",
                "name": "张三",
                "age": 25,
                "email": "test@example.com"
            }
            defaults.update(kwargs)
            return StorageData(**defaults)
        return create_test_data

    @pytest.fixture
    def storage_factory(self, tmp_path):
        """创建文件存储实例的工厂函数"""
        def create_storage():
            return TinyFileDB(
                data_dir=str(tmp_path),
                filename="test.json",
                data_class=StorageData
            )
        return create_storage

    @pytest.fixture(autouse=True)
    def setup_logging(self):
        """设置日志级别为DEBUG"""
        # 配置根日志记录器
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            force=True  # 强制重新配置
        )
        
        # 特别设置 illufly 包的日志级别
        logger = logging.getLogger('illufly')
        logger.setLevel(logging.DEBUG)
        
        # 添加控制台处理器
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            
        # 确保日志器会传播到根日志记录器
        logger.propagate = True
        
        yield
        
        # 清理处理器
        logger.handlers.clear()

    def test_set_and_get(self, storage_factory: Callable, test_data_factory: Callable):
        """测试设置和获取功能"""
        storage = storage_factory()
        test_data = test_data_factory(name="李四", age=30)
        
        storage.set(test_data, "owner1")
        result = storage.get("owner1")
        
        assert result is not None
        assert result.name == "李四"
        assert result.age == 30

    def test_list_owners(self, storage_factory: Callable, test_data_factory: Callable):
        """测试list_owners方法"""
        
        # 准备测试数据
        storage = storage_factory()
        test_data1 = test_data_factory(id="1", name="张三")
        test_data2 = test_data_factory(id="2", name="李四")
        test_data3 = test_data_factory(id="3", name="王五")
        
        # 存储数据
        storage.set(test_data1, "owner1")
        storage.set(test_data2, "owner2")
        storage.set(test_data3, "owner3")
        
        # 获取所有owner_id
        owners = storage.list_owners()
        
        # 验证结果
        assert len(owners) == 3
        assert set(owners) == {"owner1", "owner2", "owner3"}

    def test_has_duplicate(self, storage_factory: Callable, test_data_factory: Callable):
        """测试唯一性检查"""
        storage = storage_factory()
        
        # 准备测试数据
        test_data1 = test_data_factory(id="1", name="张三", email="zhangsan@test.com")
        test_data2 = test_data_factory(id="2", name="李四", email="lisi@test.com")
        
        storage.set(test_data1, "owner1")
        storage.set(test_data2, "owner2")
        
        # 测试已存在的唯一值
        assert storage.has_duplicate({"email": "zhangsan@test.com"}) == True
        
        # 测试不存在的唯一值
        assert storage.has_duplicate({"email": "wangwu@test.com"}) == False
        
        # 测试多个属性组合的唯一性
        assert storage.has_duplicate({"name": "张三", "email": "zhangsan@test.com"}) == True
        assert storage.has_duplicate({"name": "张三", "email": "other@test.com"}) == False

    def test_find(self, storage_factory: Callable, test_data_factory: Callable):
        """测试find方法"""
        storage = storage_factory()
        
        # 准备测试数据
        test_data1 = test_data_factory(id="1", name="张三", age=25)
        test_data2 = test_data_factory(id="2", name="张三", age=30)
        test_data3 = test_data_factory(id="3", name="李四", age=25)
        
        storage.set(test_data1, "owner1")
        storage.set(test_data2, "owner2")
        storage.set(test_data3, "owner3")
        
        # 测试单个条件查询
        results = storage.find({"name": "张三"})
        assert len(results) == 2
        assert {r.id for r in results} == {"1", "2"}
        
        # 测试多个条件的与查询
        results = storage.find({"name": "张三", "age": 25})
        assert len(results) == 1
        assert results[0].id == "1"
        

    def test_delete(self, storage_factory: Callable, test_data_factory: Callable, tmp_path):
        """测试删除功能"""
        storage = storage_factory()
        test_data = test_data_factory(name="张三", age=25)
        
        # 存储数据
        storage.set(test_data, "owner1")
        
        # 验证数据存在
        assert storage.get("owner1") is not None
        
        # 删除数据
        result = storage.delete("owner1")
        assert result is True  # 确认删除成功
        
        # 验证数据已被删除
        assert storage.get("owner1") is None
        assert "owner1" not in storage.list_owners()
        
        # 测试删除不存在的数据
        result = storage.delete("non_existent_owner")
        assert result is False  # 确认删除不存在的数据返回False

    def test_delete_with_multiple_files(self, storage_factory: Callable, test_data_factory: Callable, tmp_path):
        """测试在同一目录下有多个文件时的删除功能"""
        # 创建两个不同的存储实例，使用相同的owner目录但不同的文件名
        storage1 = TinyFileDB(
            data_dir=str(tmp_path),
            filename="test1.json",
            data_class=StorageData
        )
        storage2 = TinyFileDB(
            data_dir=str(tmp_path),
            filename="test2.json",
            data_class=StorageData
        )
        
        test_data = test_data_factory(name="张三", age=25)
        
        # 在同一个owner目录下存储两个文件
        storage1.set(test_data, "owner1")
        storage2.set(test_data, "owner1")
        
        # 验证两个文件都存在
        assert storage1.get("owner1") is not None
        assert storage2.get("owner1") is not None
        
        # 删除第一个文件
        result = storage1.delete("owner1")
        assert result is True
        
        # 验证只第一个文件被删除，第二个文件仍然存在
        assert storage1.get("owner1") is None
        assert storage2.get("owner1") is not None
        
        # 验证owner目录仍然存在（因为还有其他文件）
        assert (tmp_path / "owner1").exists()

# 添加新的测试数据类
@dataclass
class NestedData:
    """嵌套数据结构测试"""
    key: str
    value: str

@dataclass
class ComplexStorageData:
    """复杂数据结构测试"""
    id: str
    items: List[NestedData]
    created_at: datetime
    updated_at: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)
    
    @classmethod
    def default(cls) -> 'ComplexStorageData':
        return cls(
            id="default",
            items=[],
            created_at=datetime.utcnow()
        )
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "items": [{"key": item.key, "value": item.value} for item in self.items],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "tags": self.tags
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ComplexStorageData':
        return cls(
            id=data["id"],
            items=[NestedData(**item) for item in data["items"]],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
            tags=data.get("tags", [])
        )

class TestFileConfigStoreAdvanced:
    """高级功能测试"""
    
    @pytest.fixture
    def complex_storage_factory(self, tmp_path):
        """创建支持复杂数据的存储实例"""
        def create_storage():
            return TinyFileDB(
                data_dir=str(tmp_path),
                filename="complex_test.json",
                data_class=ComplexStorageData
            )
        return create_storage
    
    def test_complex_data_serialization(self, complex_storage_factory):
        """测试复杂数据结构的序列化"""
        storage = complex_storage_factory()
        
        # 创建测试数据
        test_data = ComplexStorageData(
            id="test1",
            items=[
                NestedData("key1", "value1"),
                NestedData("key2", "value2")
            ],
            created_at=datetime.utcnow(),
            tags=["tag1", "tag2"]
        )
        
        # 存储数据
        storage.set(test_data, "owner1")
        
        # 读取数据
        result = storage.get("owner1")
        
        # 验证结果
        assert result is not None
        assert result.id == "test1"
        assert len(result.items) == 2
        assert result.items[0].key == "key1"
        assert result.items[1].value == "value2"
        assert len(result.tags) == 2
        assert result.tags == ["tag1", "tag2"]
    
    def test_default_value_handling(self, complex_storage_factory):
        """测试默认值处理"""
        storage = complex_storage_factory()
        
        # 使用默认构造
        default_data = ComplexStorageData.default()
        storage.set(default_data, "default_owner")
        
        result = storage.get("default_owner")
        assert result is not None
        assert result.id == "default"
        assert len(result.items) == 0
        assert result.tags == []
    
    def test_datetime_handling(self, complex_storage_factory):
        """测试日期时间处理"""
        storage = complex_storage_factory()
        
        now = datetime.utcnow()
        test_data = ComplexStorageData(
            id="test_time",
            items=[],
            created_at=now,
            updated_at=now
        )
        
        storage.set(test_data, "owner_time")
        result = storage.get("owner_time")
        
        assert result is not None
        assert result.created_at.isoformat() == now.isoformat()
        assert result.updated_at is not None
        assert result.updated_at.isoformat() == now.isoformat()
    
    def test_find_with_complex_data(self, complex_storage_factory):
        """测试复杂数据的查找功能"""
        storage = complex_storage_factory()
        
        # 准备测试数据
        data1 = ComplexStorageData(
            id="1",
            items=[NestedData("tag", "python")],
            created_at=datetime.utcnow(),
            tags=["python", "web"]
        )
        data2 = ComplexStorageData(
            id="2",
            items=[NestedData("tag", "python")],
            created_at=datetime.utcnow(),
            tags=["python", "api"]
        )
        
        storage.set(data1, "owner1")
        storage.set(data2, "owner2")
        
        # 修改：使用更精确的条件匹配
        results = storage.find({
            "items": [{"key": "tag", "value": "python"}]
        })
        assert len(results) == 2
        
        # 修改：使用列表包含关系检查
        results = storage.find({
            "tags": lambda x: set(["python", "web"]).issubset(set(x))
        })
        assert len(results) == 1
        assert results[0].id == "1"
    
    def test_error_handling(self, complex_storage_factory):
        """测试错误处理"""
        storage = complex_storage_factory()
        
        # 测试无效的日期时间
        invalid_data = {
            "id": "test",
            "items": [],
            "created_at": "invalid_datetime",
            "tags": []
        }
        
        # 验证反序列化错误处理
        with pytest.raises(ValueError):
            storage._deserializer(invalid_data)

@dataclass
class AgentConfig:
    """测试用代理配置类"""
    name: str
    model: str
    created_at: datetime
    parameters: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "model": self.model,
            "created_at": self.created_at.isoformat(),
            "parameters": self.parameters,
            "is_active": self.is_active
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'AgentConfig':
        return cls(
            name=data["name"],
            model=data["model"],
            created_at=datetime.fromisoformat(data["created_at"]),
            parameters=data.get("parameters", {}),
            is_active=data.get("is_active", True)
        )

class TestFileConfigStoreCompositeTypes:
    """测试复合类型存储"""
    
    @pytest.fixture
    def agent_config_factory(self):
        def create_config(**kwargs) -> AgentConfig:
            defaults = {
                "name": "test_agent",
                "model": "gpt-3.5",
                "created_at": datetime.utcnow(),
                "parameters": {"temperature": 0.7}
            }
            defaults.update(kwargs)
            return AgentConfig(**defaults)
        return create_config
    
    def test_dict_storage(self, tmp_path, agent_config_factory):
        """测试字典类型存储"""
        # 创建配置字典存储
        store = TinyFileDB(
            data_dir=str(tmp_path),
            filename="agents.json",
            data_class=Dict[str, AgentConfig]
        )
        
        # 准备测试数据
        config1 = agent_config_factory(name="agent1")
        config2 = agent_config_factory(name="agent2", model="gpt-4")
        
        # 存储数据
        test_data = {
            "agent1": config1,
            "agent2": config2
        }
        store.set(test_data, "user1")
        
        # 读取并验证
        loaded = store.get("user1")
        assert loaded is not None
        assert isinstance(loaded, dict)
        assert len(loaded) == 2
        assert loaded["agent1"].name == "agent1"
        assert loaded["agent2"].model == "gpt-4"
        
        # 测试部分更新
        config3 = agent_config_factory(name="agent3")
        loaded["agent3"] = config3
        store.set(loaded, "user1")
        
        updated = store.get("user1")
        assert len(updated) == 3
        assert updated["agent3"].name == "agent3"
    
    def test_list_storage(self, tmp_path, agent_config_factory):
        """测试列表类型存储"""
        store = TinyFileDB(
            data_dir=str(tmp_path),
            filename="agent_list.json",
            data_class=List[AgentConfig]
        )
        
        # 准备测试数据
        configs = [
            agent_config_factory(name=f"agent{i}")
            for i in range(3)
        ]
        
        # 存储数据
        store.set(configs, "user1")
        
        # 读取并验证
        loaded = store.get("user1")
        assert loaded is not None
        assert isinstance(loaded, list)
        assert len(loaded) == 3
        assert all(isinstance(item, AgentConfig) for item in loaded)
        assert [item.name for item in loaded] == ["agent0", "agent1", "agent2"]
    
    def test_nested_dict_storage(self, tmp_path, agent_config_factory):
        """测试嵌套字典存储"""
        store = TinyFileDB(
            data_dir=str(tmp_path),
            filename="nested_agents.json",
            data_class=Dict[str, Dict[str, AgentConfig]]
        )
        
        # 准备测试数据
        test_data = {
            "project1": {
                "agent1": agent_config_factory(name="agent1"),
                "agent2": agent_config_factory(name="agent2")
            },
            "project2": {
                "agent3": agent_config_factory(name="agent3")
            }
        }
        
        # 存储数据
        store.set(test_data, "user1")
        
        # 读取并验证
        loaded = store.get("user1")
        assert loaded is not None
        assert isinstance(loaded, dict)
        assert len(loaded) == 2
        assert isinstance(loaded["project1"], dict)
        assert len(loaded["project1"]) == 2
        assert loaded["project1"]["agent1"].name == "agent1"
    
    def test_find_in_composite_types(self, tmp_path, agent_config_factory):
        """测试复合类型的查找功能"""
        store = TinyFileDB(
            data_dir=str(tmp_path),
            filename="searchable_agents.json",
            data_class=Dict[str, AgentConfig]
        )
        
        # 准备测试数据
        test_data = {
            "agent1": agent_config_factory(
                name="agent1",
                model="gpt-3.5",
                parameters={"temperature": 0.7}
            ),
            "agent2": agent_config_factory(
                name="agent2",
                model="gpt-4",
                parameters={"temperature": 0.9}
            )
        }
        store.set(test_data, "user1")
        
        # 测试基于模型的查找
        results = store.find({"model": "gpt-4"})
        assert len(results) == 1
        assert list(results)[0]["agent2"].name == "agent2"
        
        # 测试基于参数的查找
        results = store.find({
            "parameters": lambda p: p.get("temperature", 0) > 0.8
        })
        assert len(results) == 1
        assert list(results)[0]["agent2"].parameters["temperature"] == 0.9
    
    def test_complex_nested_structures(self, tmp_path, agent_config_factory):
        """测试复杂嵌套结构"""
        store = TinyFileDB(
            data_dir=str(tmp_path),
            filename="complex_agents.json",
            data_class=Dict[str, List[Dict[str, AgentConfig]]]
        )
        
        # 准备测试数据
        test_data = {
            "project1": [
                {
                    "main": agent_config_factory(name="agent1"),
                    "backup": agent_config_factory(name="agent1_backup")
                },
                {
                    "main": agent_config_factory(name="agent2"),
                    "backup": agent_config_factory(name="agent2_backup")
                }
            ],
            "project2": [
                {
                    "main": agent_config_factory(name="agent3")
                }
            ]
        }
        
        # 存储数据
        store.set(test_data, "user1")
        
        # 读取并验证
        loaded = store.get("user1")
        assert loaded is not None
        assert isinstance(loaded, dict)
        assert len(loaded["project1"]) == 2
        assert loaded["project1"][0]["main"].name == "agent1"
        assert loaded["project1"][1]["backup"].name == "agent2_backup"
        assert loaded["project2"][0]["main"].name == "agent3"

    def test_list_and_tuple_storage(self, tmp_path, agent_config_factory):
        """测试列表和元组类型存储"""
        # 创建列表存储
        list_store = TinyFileDB(
            data_dir=str(tmp_path),
            filename="list_test.json",
            data_class=List[str]
        )
        
        # 创建元组存储
        tuple_store = TinyFileDB(
            data_dir=str(tmp_path),
            filename="tuple_test.json",
            data_class=tuple[str, int, bool]  # Python 3.9+
        )
        
        # 测试列表存储
        test_list = ["item1", "item2", "item3"]
        list_store.set(test_list, "owner1")
        
        # 测试元组存储
        test_tuple = ("test", 42, True)
        tuple_store.set(test_tuple, "owner1")
        
        # 验证列表存储
        loaded_list = list_store.get("owner1")
        assert loaded_list is not None
        assert isinstance(loaded_list, list)
        assert loaded_list == test_list
        
        # 验证元组存储
        loaded_tuple = tuple_store.get("owner1")
        assert loaded_tuple is not None
        assert isinstance(loaded_tuple, tuple)
        assert loaded_tuple == test_tuple
        assert loaded_tuple[0] == "test"
        assert loaded_tuple[1] == 42
        assert loaded_tuple[2] is True

    def test_nested_list_storage(self, tmp_path, agent_config_factory):
        """测试嵌套列表存储"""
        # 创建嵌套列表存储
        nested_store = TinyFileDB(
            data_dir=str(tmp_path),
            filename="nested_list.json",
            data_class=List[List[str]]
        )
        
        # 准备测试数据
        test_data = [
            ["a1", "a2", "a3"],
            ["b1", "b2"],
            ["c1", "c2", "c3", "c4"]
        ]
        
        # 存储数据
        nested_store.set(test_data, "owner1")
        
        # 读取并验证
        loaded = nested_store.get("owner1")
        assert loaded is not None
        assert isinstance(loaded, list)
        assert all(isinstance(item, list) for item in loaded)
        assert loaded == test_data
        assert len(loaded[0]) == 3
        assert len(loaded[1]) == 2
        assert len(loaded[2]) == 4
        assert loaded[0][0] == "a1"

class PydanticNestedData(BaseModel):
    """Pydantic嵌套数据结构"""
    key: str
    value: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class PydanticComplexData(BaseModel):
    """Pydantic复杂数据结构"""
    id: str
    items: List[PydanticNestedData] = Field(default_factory=list)
    metadata: Dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    tags: List[str] = Field(default_factory=list)

class TestPydanticSupport:
    """测试Pydantic模型支持"""
    
    @pytest.fixture
    def pydantic_storage_factory(self, tmp_path):
        """创建支持Pydantic的存储实例"""
        def create_storage():
            return TinyFileDB(
                data_dir=str(tmp_path),
                filename="pydantic_test.json",
                data_class=PydanticComplexData
            )
        return create_storage

    def test_basic_pydantic_operations(self, pydantic_storage_factory):
        """测试基本的Pydantic模型操作"""
        storage = pydantic_storage_factory()
        
        # 创建测试数据
        nested_item = PydanticNestedData(
            key="test_key",
            value="test_value"
        )
        
        test_data = PydanticComplexData(
            id="test1",
            items=[nested_item],
            metadata={"version": "1.0"},
            tags=["test", "pydantic"]
        )
        
        # 存储数据
        storage.set(test_data, "owner1")
        
        # 读取数据
        result = storage.get("owner1")
        
        # 验证结果
        assert result is not None
        assert isinstance(result, PydanticComplexData)
        assert result.id == "test1"
        assert len(result.items) == 1
        assert result.items[0].key == "test_key"
        assert result.metadata["version"] == "1.0"
        assert set(result.tags) == {"test", "pydantic"}

    def test_pydantic_composite_types(self, tmp_path):
        """测试Pydantic复合类型"""
        # 创建字典存储
        dict_store = TinyFileDB(
            data_dir=str(tmp_path),
            filename="pydantic_dict.json",
            data_class=Dict[str, PydanticComplexData]
        )
        
        # 创建列表存储
        list_store = TinyFileDB(
            data_dir=str(tmp_path),
            filename="pydantic_list.json",
            data_class=List[PydanticComplexData]
        )
        
        # 测试字典存储
        dict_data = {
            "item1": PydanticComplexData(
                id="1",
                metadata={"type": "test"}
            ),
            "item2": PydanticComplexData(
                id="2",
                metadata={"type": "prod"}
            )
        }
        dict_store.set(dict_data, "owner1")
        
        # 测试列表存储
        list_data = [
            PydanticComplexData(id="1", tags=["test"]),
            PydanticComplexData(id="2", tags=["prod"])
        ]
        list_store.set(list_data, "owner1")
        
        # 验证字典存储
        dict_result = dict_store.get("owner1")
        assert dict_result is not None
        assert isinstance(dict_result, dict)
        assert len(dict_result) == 2
        assert all(isinstance(v, PydanticComplexData) for v in dict_result.values())
        
        # 验证列表存储
        list_result = list_store.get("owner1")
        assert list_result is not None
        assert isinstance(list_result, list)
        assert len(list_result) == 2
        assert all(isinstance(v, PydanticComplexData) for v in list_result)

    def test_pydantic_find_operations(self, pydantic_storage_factory):
        """测试Pydantic模型的查找操作"""
        storage = pydantic_storage_factory()
        
        # 准备测试数据
        data1 = PydanticComplexData(
            id="1",
            metadata={"env": "dev"},
            tags=["python", "test"]
        )
        data2 = PydanticComplexData(
            id="2",
            metadata={"env": "prod"},
            tags=["python", "prod"]
        )
        
        storage.set(data1, "owner1")
        storage.set(data2, "owner2")
        
        # 测试简单查找
        results = storage.find({"id": "1"})
        assert len(results) == 1
        assert results[0].metadata["env"] == "dev"
        
        # 测试复杂查找
        results = storage.find({
            "tags": lambda x: "python" in x and "test" in x
        })
        assert len(results) == 1
        assert results[0].id == "1"
        
        # 测试嵌套字段查找
        results = storage.find({
            "metadata": {"env": "prod"}
        })
        assert len(results) == 1
        assert results[0].id == "2"

    def test_pydantic_datetime_handling(self, pydantic_storage_factory):
        """测试Pydantic模型的日期时间处理"""
        storage = pydantic_storage_factory()
        
        now = datetime.utcnow()
        test_data = PydanticComplexData(
            id="test_time",
            created_at=now,
            updated_at=now
        )
        
        # 存储数据
        storage.set(test_data, "owner1")
        
        # 读取数据
        result = storage.get("owner1")
        
        # 验证日期时间字段
        assert result is not None
        assert isinstance(result.created_at, datetime)
        assert isinstance(result.updated_at, datetime)
        assert result.created_at.isoformat() == now.isoformat()
        assert result.updated_at.isoformat() == now.isoformat()

    def test_pydantic_validation(self, pydantic_storage_factory):
        """测试Pydantic模型的验证功能"""
        storage = pydantic_storage_factory()
        
        # 测试必填字段
        with pytest.raises(ValueError):
            PydanticComplexData()  # id 是必填字段
        
        # 测试字段类型验证
        with pytest.raises(ValueError):
            PydanticComplexData(
                id="test",
                items=[{"invalid": "data"}]  # items 必须是 PydanticNestedData 对象列表
            )
        
        # 测试有效数据
        valid_data = PydanticComplexData(
            id="test",
            items=[
                PydanticNestedData(key="k1", value="v1")
            ]
        )
        storage.set(valid_data, "owner1")
        
        result = storage.get("owner1")
        assert result is not None
        assert result.id == "test"
        assert len(result.items) == 1

class TestFileConfigStoreIndexing:
    """测试FileConfigStore的索引功能
    
    主要测试场景：
    1. 索引的基本功能：
       - find方法自动使用索引进行查询
       - 混合索引和非索引字段的查询
       - 索引查询的性能提升
    
    2. 索引的内部机制：
       - 索引数据结构的维护
       - 索引的更新机制
       - 数据删除时的索引更新
    
    3. 索引的持久化：
       - 索引数据的存储格式
       - 索引的自动加载
       - 错误处理
    """
    
    @pytest.fixture
    def indexed_storage_factory(self, tmp_path):
        """创建带索引的存储实例"""
        def create_storage(indexes=None, cache_size=1000):
            return TinyFileDB(
                data_dir=str(tmp_path),
                filename="indexed_test.json",
                data_class=StorageData,
                indexes=indexes or [],
                cache_size=cache_size
            )
        return create_storage

    def test_find_auto_uses_index(self, indexed_storage_factory):
        """测试find方法自动使用索引"""
        storage = indexed_storage_factory(indexes=["email"])
        
        # 存储测试数据
        for i in range(5):
            data = StorageData(
                id=str(i),
                name=f"user{i}",
                email=f"user{i}@test.com"
            )
            storage.set(data, f"owner{i}")
        
        # 使用索引字段查询时应该走索引
        with patch.object(storage, '_find_with_index') as mock_index_find:
            mock_index_find.return_value = ["owner2"]
            results = storage.find({"email": "user2@test.com"})
            
            # 验证确实调用了索引查询
            mock_index_find.assert_called_once_with("email", "user2@test.com")
            assert len(results) == 1
            assert results[0].id == "2"
        
        # 使用非索引字段时不应该走索引
        with patch.object(storage, '_find_with_index') as mock_index_find:
            results = storage.find({"name": "user3"})
            mock_index_find.assert_not_called()
            assert len(results) == 1
            assert results[0].id == "3"

    def test_multiple_conditions_with_index(self, indexed_storage_factory):
        """测试多条件查询（包含索引和非索引字段）"""
        storage = indexed_storage_factory(indexes=["email"])
        
        # 存储测试数据
        data1 = StorageData(id="1", name="张三", email="zhangsan@test.com", age=25)
        data2 = StorageData(id="2", name="张三", email="zhangsan2@test.com", age=30)
        
        storage.set(data1, "owner1")
        storage.set(data2, "owner2")
        
        # 组合索引和非索引字段查询
        results = storage.find({
            "email": "zhangsan@test.com",  # 索引字段
            "age": 25  # 非索引字段
        })
        assert len(results) == 1
        assert results[0].id == "1"

    def test_index_performance(self, indexed_storage_factory):
        """测试索引性能提升"""
        storage_with_index = indexed_storage_factory(indexes=["email"], cache_size=0)
        storage_without_index = indexed_storage_factory(cache_size=0)
        
        # 存储大量测试数据
        for i in range(100):
            data = StorageData(
                id=str(i),
                name=f"user{i}",
                email=f"user{i}@test.com"
            )
            storage_with_index.set(data, f"owner{i}")
            storage_without_index.set(data, f"owner{i}")
        
        # 测试查询性能
        import time
        
        start_time = time.time()
        results_with_index = storage_with_index.find({"email": "user99@test.com"})
        index_time = time.time() - start_time
        
        start_time = time.time()
        results_without_index = storage_without_index.find({"email": "user99@test.com"})
        no_index_time = time.time() - start_time
        
        # 验证结果正确性和性能提升
        assert len(results_with_index) == len(results_without_index) == 1
        assert results_with_index[0].id == "99"
        assert index_time < no_index_time

    def test_index_structure(self, indexed_storage_factory):
        """测试索引结构的正确性"""
        storage = indexed_storage_factory(indexes=["email", "name"])
        
        # 存储测试数据
        data1 = StorageData(id="1", name="张三", email="zhangsan@test.com")
        data2 = StorageData(id="2", name="张三", email="zhangsan2@test.com")
        
        storage.set(data1, "owner1")
        storage.set(data2, "owner2")
        
        # 验证索引结构
        assert storage._indexes["email"] == {
            "zhangsan@test.com": ["owner1"],
            "zhangsan2@test.com": ["owner2"]
        }
        assert storage._indexes["name"] == {
            "张三": ["owner1", "owner2"]
        }

    def test_index_update_internal(self, indexed_storage_factory):
        """测试索引更新的内部逻辑"""
        storage = indexed_storage_factory(indexes=["email"])
        
        # 添加初始数据
        data = StorageData(id="1", name="张三", email="zhangsan@test.com")
        storage.set(data, "owner1")
        
        # 验证初始索引
        assert storage._indexes["email"]["zhangsan@test.com"] == ["owner1"]
        
        # 更新数据
        updated_data = StorageData(id="1", name="张三", email="zhangsan_new@test.com")
        storage.set(updated_data, "owner1")
        
        # 验证索引更新
        assert "zhangsan@test.com" not in storage._indexes["email"]
        assert storage._indexes["email"]["zhangsan_new@test.com"] == ["owner1"]

    def test_delete_with_index(self, indexed_storage_factory):
        """测试删除时索引自动更新"""
        storage = indexed_storage_factory(indexes=["email"])
        
        data = StorageData(id="1", name="张三", email="zhangsan@test.com")
        storage.set(data, "owner1")
        
        # 删除数据并验证索引更新
        storage.delete("owner1")
        assert "zhangsan@test.com" not in storage._indexes["email"]
        assert storage.find({"email": "zhangsan@test.com"}) == []

    def test_index_persistence_format(self, indexed_storage_factory, tmp_path):
        """测试索引持久化格式"""
        storage = indexed_storage_factory(indexes=["email"])
        
        data = StorageData(id="1", name="张三", email="zhangsan@test.com")
        storage.set(data, "owner1")
        
        # 验证索引文件
        index_file = tmp_path / ".indexes" / "indexed_test.json"
        assert index_file.exists()
        
        with open(index_file, 'r', encoding='utf-8') as f:
            index_data = json.load(f)
            assert "email" in index_data
            assert index_data["email"]["zhangsan@test.com"] == ["owner1"]

    def test_index_load_on_init(self, indexed_storage_factory, tmp_path):
        """测试初始化时加载索引"""
        # 第一个实例创建索引
        storage1 = indexed_storage_factory(indexes=["email"])
        data = StorageData(id="1", name="张三", email="zhangsan@test.com")
        storage1.set(data, "owner1")
        
        # 创建新实例并验证索引加载
        storage2 = indexed_storage_factory(indexes=["email"])
        assert "email" in storage2._indexes
        assert storage2._indexes["email"]["zhangsan@test.com"] == ["owner1"]
        
        # 验证索引可用
        results = storage2.find({"email": "zhangsan@test.com"})
        assert len(results) == 1
        assert results[0].id == "1"

    def test_invalid_index_field(self, indexed_storage_factory):
        """测试无效索引字段处理"""
        with pytest.raises(ValueError) as exc_info:
            storage = indexed_storage_factory(indexes=["non_existent_field"])
        assert "无效的索引字段" in str(exc_info.value)

class TestFileConfigStoreCache:
    """测试FileConfigStore的缓存功能"""
    
    @pytest.fixture
    def cached_storage_factory(self, tmp_path):
        def create_storage(cache_size=10):
            return TinyFileDB(
                data_dir=str(tmp_path),
                filename="cached_test.json",
                data_class=StorageData,
                cache_size=cache_size
            )
        return create_storage

    def test_cache_hit(self, cached_storage_factory, tmp_path):
        """测试缓存命中"""
        storage = cached_storage_factory()
        
        # 存储测试数据
        data = StorageData(id="1", name="test", email="test@example.com")
        storage.set(data, "owner1")
        
        # 清除缓存，确保第一次需要从文件加载
        storage.clear_cache()
        
        # 记录实际的文件路径
        real_file_path = storage._get_file_path("owner1")
        
        # 第一次获取（从文件加载）
        with patch.object(storage, '_get_file_path') as mock_get_path:
            # 设置mock返回实际的文件路径
            mock_get_path.return_value = real_file_path
            
            result1 = storage.get("owner1")
            assert result1.id == "1"
            mock_get_path.assert_called_once()
        
        # 第二次获取（应该从缓存加载）
        with patch.object(storage, '_get_file_path') as mock_get_path:
            result2 = storage.get("owner1")
            assert result2.id == "1"
            mock_get_path.assert_not_called()

    def test_cache_eviction(self, cached_storage_factory):
        """测试缓存淘汰"""
        storage = cached_storage_factory(cache_size=2)
        
        # 存储3条数据（超过缓存容量）
        for i in range(3):
            data = StorageData(id=str(i), name=f"test{i}", email=f"test{i}@example.com")
            storage.set(data, f"owner{i}")
        
        # 验证缓存信息
        cache_info = storage.get_cache_info()
        assert cache_info["size"] == 2
        assert cache_info["capacity"] == 2

    def test_cache_update(self, cached_storage_factory):
        """测试缓存更新"""
        storage = cached_storage_factory()
        
        # 存储初始数据
        data1 = StorageData(id="1", name="test", email="test@example.com")
        storage.set(data1, "owner1")
        
        # 更新数据
        data2 = StorageData(id="1", name="updated", email="test@example.com")
        storage.set(data2, "owner1")
        
        # 验证缓存是否更新
        result = storage.get("owner1")
        assert result.name == "updated"

    def test_cache_clear(self, cached_storage_factory):
        """测试缓存清理"""
        storage = cached_storage_factory()
        
        # 存储测试数据
        data = StorageData(id="1", name="test", email="test@example.com")
        storage.set(data, "owner1")
        
        # 清除缓存
        storage.clear_cache()
        
        # 验证需要重新从文件加载
        with patch.object(storage, '_get_file_path') as mock_get_path:
            storage.get("owner1")
            mock_get_path.assert_called_once()

    def test_indexed_search_with_cache(self, cached_storage_factory):
        """测试索引搜索与缓存交互"""
        storage = cached_storage_factory(cache_size=5)
        storage._index_fields = ["email"]  # 启用索引
        
        # 存储测试数据
        for i in range(10):
            data = StorageData(
                id=str(i),
                name=f"user{i}",
                email=f"user{i}@test.com"
            )
            storage.set(data, f"owner{i}")
        
        # 使用索引查询
        results = storage.find({"email": "user5@test.com"})
        assert len(results) == 1
        assert results[0].id == "5"
        
        # 验证缓存大小没有超出限制
        cache_info = storage.get_cache_info()
        assert cache_info["size"] <= cache_info["capacity"]