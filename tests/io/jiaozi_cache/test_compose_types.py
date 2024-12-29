from dataclasses import dataclass, field
from typing import (
    Callable, Dict, Any, List, Tuple, Set, 
    Union, Optional, FrozenSet
)
from datetime import datetime
import pytest
import logging

from illufly.io import JiaoziCache, IndexType

@dataclass
class AgentConfig:
    """测试用代理配置类"""
    name: str
    model: str
    created_at: datetime
    parameters: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    tags: Set[str] = field(default_factory=set)  # 添加集合类型字段
    backup_models: Tuple[str, ...] = field(default_factory=tuple)  # 添加元组类型字段
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "model": self.model,
            "created_at": self.created_at.isoformat(),
            "parameters": self.parameters,
            "is_active": self.is_active,
            "tags": list(self.tags),
            "backup_models": list(self.backup_models)
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'AgentConfig':
        return cls(
            name=data["name"],
            model=data["model"],
            created_at=datetime.fromisoformat(data["created_at"]),
            parameters=data.get("parameters", {}),
            is_active=data.get("is_active", True),
            tags=set(data.get("tags", [])),
            backup_models=tuple(data.get("backup_models", []))
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
        store = JiaoziCache.create_with_json_storage(
            data_dir=str(tmp_path),
            filename="agents.json",
            data_class=Dict[str, AgentConfig]
        )
        
        # 准备测试数据
        config1 = agent_config_factory(name="agent1")
        config2 = agent_config_factory(name="agent2", model="gpt-4")
        
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
        store = JiaoziCache.create_with_json_storage(
            data_dir=str(tmp_path),
            filename="agent_list.json",
            data_class=List[AgentConfig]
        )
        
        configs = [
            agent_config_factory(name=f"agent{i}")
            for i in range(3)
        ]
        
        store.set(configs, "user1")
        
        loaded = store.get("user1")
        assert loaded is not None
        assert isinstance(loaded, list)
        assert len(loaded) == 3
        assert all(isinstance(item, AgentConfig) for item in loaded)
        assert [item.name for item in loaded] == ["agent0", "agent1", "agent2"]

    def test_nested_dict_storage(self, tmp_path, agent_config_factory):
        """测试嵌套字典存储"""
        store = JiaoziCache.create_with_json_storage(
            data_dir=str(tmp_path),
            filename="nested_agents.json",
            data_class=Dict[str, Dict[str, AgentConfig]]
        )
        
        test_data = {
            "project1": {
                "agent1": agent_config_factory(name="agent1"),
                "agent2": agent_config_factory(name="agent2")
            },
            "project2": {
                "agent3": agent_config_factory(name="agent3")
            }
        }
        
        store.set(test_data, "user1")
        
        loaded = store.get("user1")
        assert loaded is not None
        assert isinstance(loaded, dict)
        assert len(loaded) == 2
        assert isinstance(loaded["project1"], dict)
        assert len(loaded["project1"]) == 2
        assert loaded["project1"]["agent1"].name == "agent1"

    def test_find_in_composite_types(self, tmp_path, agent_config_factory, caplog):
        """测试复合类型的查找功能"""
        # 设置日志级别为 DEBUG
        caplog.set_level(logging.DEBUG)
        
        # 直接指定字段类型
        field_types = {
            "model": str,
            "parameters.temperature": float,
            "is_active": bool
        }
        
        store = JiaoziCache.create_with_json_storage(
            data_dir=str(tmp_path),
            filename="searchable_agents.json",
            data_class=Dict[str, AgentConfig],
            field_types=field_types,  # 显式指定字段类型
            index_config={
                "model": IndexType.HASH,
                "parameters.temperature": IndexType.BTREE,
                "is_active": IndexType.HASH
            }
        )
        
        # 打印调试信息
        print("\n=== Debug Information ===")
        print(f"Data Class: {store._data_class}")
        print(f"Field Types: {field_types}")
        print("=== Log Messages ===")
        for record in caplog.records:
            print(f"{record.levelname}: {record.message}")
        print("=====================")
        
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
        results = store.query({"model": "gpt-4"})
        assert len(results) == 1
        assert results[0]["agent2"].model == "gpt-4"
        
        # 测试基于参数的范围查询
        results = store.query({
            "parameters.temperature": (">=", 0.8)
        })
        assert len(results) == 1
        assert results[0]["agent2"].parameters["temperature"] == 0.9

    def test_complex_nested_structures(self, tmp_path, agent_config_factory):
        """测试复杂嵌套结构"""
        store = JiaoziCache.create_with_json_storage(
            data_dir=str(tmp_path),
            filename="complex_agents.json",
            data_class=Dict[str, List[Dict[str, AgentConfig]]]
        )
        
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
        
        store.set(test_data, "user1")
        
        loaded = store.get("user1")
        assert loaded is not None
        assert isinstance(loaded, dict)
        assert len(loaded["project1"]) == 2
        assert loaded["project1"][0]["main"].name == "agent1"
        assert loaded["project1"][1]["backup"].name == "agent2_backup"
        assert loaded["project2"][0]["main"].name == "agent3"

    def test_serialization_error_handling(self, tmp_path, agent_config_factory):
        """测试序列化错误处理"""
        store = JiaoziCache.create_with_json_storage(
            data_dir=str(tmp_path),
            filename="error_test.json",
            data_class=Dict[str, AgentConfig]
        )
        
        # 创建一个无法序列化的对象
        bad_config = agent_config_factory()
        bad_config.parameters = {"bad_value": object()}  # 无法JSON序列化的对象
        
        with pytest.raises(TypeError):
            store.set({"bad": bad_config}, "user1")

    def test_deserialization_error_handling(self, tmp_path, agent_config_factory):
        """测试反序列化错误处理"""
        store = JiaoziCache.create_with_json_storage(
            data_dir=str(tmp_path),
            filename="error_test.json",
            data_class=Dict[str, AgentConfig],
            cache_size=0  # 禁用缓存以测试文件读取
        )

        # 直接写入损坏的 JSON 文件
        file_path = tmp_path / "user1" / "error_test.json"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w") as f:
            f.write('{"invalid": "json"')  # 不完整的JSON

        # 验证读取时的错误处理
        result = store.get("user1")
        assert result is None  # 验证错误时返回 None

    def test_tuple_types(self, tmp_path, agent_config_factory):
        """测试元组类型存储"""
        store = JiaoziCache.create_with_json_storage(
            data_dir=str(tmp_path),
            filename="tuple_agents.json",
            data_class=Tuple[AgentConfig, AgentConfig]  # 固定长度的代理配置对
        )
        
        # 创建代理配置对
        primary = agent_config_factory(
            name="primary",
            model="gpt-4",
            tags={"production", "primary"}
        )
        backup = agent_config_factory(
            name="backup",
            model="gpt-3.5",
            tags={"backup"}
        )
        
        # 存储配置对
        store.set((primary, backup), "agent_pair")
        
        # 读取并验证
        loaded = store.get("agent_pair")
        assert isinstance(loaded, tuple)
        assert len(loaded) == 2
        assert loaded[0].name == "primary"
        assert loaded[1].name == "backup"
        assert loaded[0].tags == {"production", "primary"}

    def test_set_types(self, tmp_path):
        """测试集��类型存储"""
        store = JiaoziCache.create_with_json_storage(
            data_dir=str(tmp_path),
            filename="agent_tags.json",
            data_class=Dict[str, Set[str]]
        )
        
        # 存储标签集合
        tags = {
            "agent1": {"production", "active", "gpt4"},
            "agent2": {"development", "testing"}
        }
        store.set(tags, "project_tags")
        
        # 读取并验证
        loaded = store.get("project_tags")
        assert isinstance(loaded, dict)
        assert isinstance(loaded["agent1"], set)
        assert loaded["agent1"] == {"production", "active", "gpt4"}
        assert loaded["agent2"] == {"development", "testing"}

    def test_union_types(self, tmp_path, agent_config_factory):
        """测试联合类型存储"""
        store = JiaoziCache.create_with_json_storage(
            data_dir=str(tmp_path),
            filename="mixed_agents.json",
            data_class=Dict[str, Union[AgentConfig, List[AgentConfig]]]
        )
        
        # 准备混合类型数据
        primary = agent_config_factory(name="primary", model="gpt-4")
        backups = [
            agent_config_factory(name=f"backup_{i}", model="gpt-3.5")
            for i in range(2)
        ]
        
        test_data = {
            "primary": primary,
            "backups": backups
        }
        
        store.set(test_data, "mixed_config")
        
        # 读取并验证
        loaded = store.get("mixed_config")
        assert isinstance(loaded["primary"], AgentConfig)
        assert isinstance(loaded["backups"], list)
        assert loaded["primary"].name == "primary"
        assert len(loaded["backups"]) == 2
        assert loaded["backups"][0].name == "backup_0"

    def test_frozen_set_types(self, tmp_path):
        """测试不可变集合类型存储"""
        store = JiaoziCache.create_with_json_storage(
            data_dir=str(tmp_path),
            filename="frozen_tags.json",
            data_class=Dict[str, FrozenSet[str]]
        )
        
        # 存储不可变标签集合
        tags = {
            "agent1": frozenset({"prod", "stable"}),
            "agent2": frozenset({"dev", "testing"})
        }
        store.set(tags, "frozen_tags")
        
        # 读取并验证
        loaded = store.get("frozen_tags")
        assert isinstance(loaded, dict)
        assert isinstance(loaded["agent1"], frozenset)
        assert loaded["agent1"] == frozenset({"prod", "stable"})
        assert loaded["agent2"] == frozenset({"dev", "testing"})

    def test_optional_types(self, tmp_path, agent_config_factory):
        """测试可选类型存储"""
        store = JiaoziCache.create_with_json_storage(
            data_dir=str(tmp_path),
            filename="optional_agents.json",
            data_class=Dict[str, Optional[AgentConfig]]
        )
        
        # 准备包含空值的数据
        test_data = {
            "active": agent_config_factory(name="active"),
            "inactive": None
        }
        
        store.set(test_data, "optional_config")
        
        # 读取并验证
        loaded = store.get("optional_config")
        assert isinstance(loaded, dict)
        assert loaded["active"] is not None
        assert loaded["active"].name == "active"
        assert loaded["inactive"] is None