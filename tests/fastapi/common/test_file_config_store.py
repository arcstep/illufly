import pytest
from dataclasses import dataclass
from typing import Callable
from illufly.fastapi.common import FileConfigStore
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass(frozen=True)
class StorageData:
    """测试用数据类"""
    id: str = "1"
    name: str = "张三"
    age: int = 25
    email: str = "test@example.com"

@pytest.fixture
def test_data_factory():
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
def storage_factory(tmp_path):
    """创建文件存储实例的工厂函数"""
    def create_storage():
        return FileConfigStore(
            data_dir=str(tmp_path),
            filename="test.json",
            data_class=StorageData,
            serializer=lambda x: x.__dict__,
            deserializer=lambda x: StorageData(**x)
        )
    return create_storage

def test_set_and_get(storage_factory: Callable, test_data_factory: Callable):
    """测试设置和获取功能"""
    storage = storage_factory()
    test_data = test_data_factory(name="李四", age=30)
    
    storage.set(test_data, "owner1")
    result = storage.get("owner1")
    
    assert result is not None
    assert result.name == "李四"
    assert result.age == 30

def test_list_owners(storage_factory: Callable, test_data_factory: Callable):
    """测试list_owners方法"""
    storage = storage_factory()
    
    # 准备测试数据
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

def test_has_duplicate(storage_factory: Callable, test_data_factory: Callable):
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

def test_find(storage_factory: Callable, test_data_factory: Callable):
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
    
    # 测试指定owner_id的查询
    results = storage.find({"name": "张三"}, "owner1")
    assert len(results) == 1
    assert results[0].id == "1"

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
            return FileConfigStore(
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
        store = FileConfigStore[Dict[str, AgentConfig]](
            data_dir=str(tmp_path),
            filename="agents.json"
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
        store = FileConfigStore[List[AgentConfig]](
            data_dir=str(tmp_path),
            filename="agent_list.json"
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
        store = FileConfigStore[Dict[str, Dict[str, AgentConfig]]](
            data_dir=str(tmp_path),
            filename="nested_agents.json"
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
        store = FileConfigStore[Dict[str, AgentConfig]](
            data_dir=str(tmp_path),
            filename="searchable_agents.json"
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
        results = store.find({"model": "gpt-4"}, "user1")
        assert len(results) == 1
        assert list(results)[0]["agent2"].name == "agent2"
        
        # 测试基于参数的查找
        results = store.find({
            "parameters": lambda p: p.get("temperature", 0) > 0.8
        }, "user1")
        assert len(results) == 1
        assert list(results)[0]["agent2"].parameters["temperature"] == 0.9
    
    def test_complex_nested_structures(self, tmp_path, agent_config_factory):
        """测试复杂嵌套结构"""
        store = FileConfigStore[Dict[str, List[Dict[str, AgentConfig]]]](
            data_dir=str(tmp_path),
            filename="complex_agents.json"
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

