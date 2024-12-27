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

from illufly.io import JiaoziCache
from pydantic import BaseModel, Field
from illufly.io.jiaozi_cache.backend import JSONFileStorageBackend
from illufly.io.jiaozi_cache.index import HashIndexBackend


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
        store = JiaoziCache(
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
        store = JiaoziCache(
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
        store = JiaoziCache(
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
        store = JiaoziCache(
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
        store = JiaoziCache(
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
        list_store = JiaoziCache(
            data_dir=str(tmp_path),
            filename="list_test.json",
            data_class=List[str]
        )
        
        # 创建元组存储
        tuple_store = JiaoziCache(
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
        nested_store = JiaoziCache(
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