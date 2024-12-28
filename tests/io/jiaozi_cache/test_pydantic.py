from datetime import datetime
from typing import List, Optional, Dict
import pytest
from pydantic import BaseModel, Field

from illufly.io import JiaoziCache

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
            return JiaoziCache.create_with_json_storage(
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
        assert result.tags == ["test", "pydantic"]

    def test_pydantic_composite_types(self, tmp_path):
        """测试Pydantic复合类型"""
        # 创建字典存储
        dict_store = JiaoziCache.create_with_json_storage(
            data_dir=str(tmp_path),
            filename="pydantic_dict.json",
            data_class=Dict[str, PydanticComplexData]
        )
        
        # 创建列表存储
        list_store = JiaoziCache.create_with_json_storage(
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
        results = list(storage.query({"id": "1"}))
        assert len(results) == 1
        assert results[0].metadata["env"] == "dev"
        
        # 测试复杂查找
        results = list(storage.query({
            "tags": lambda x: "python" in x and "test" in x
        }))
        assert len(results) == 1
        assert results[0].id == "1"

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
        assert result.created_at.isoformat()[:19] == now.isoformat()[:19]  # 比较到秒级
        assert result.updated_at.isoformat()[:19] == now.isoformat()[:19]

    def test_pydantic_validation(self, pydantic_storage_factory):
        """测试Pydantic模型的验证功能"""
        storage = pydantic_storage_factory()
        
        # 测试必填字段
        with pytest.raises(ValueError):
            PydanticComplexData()  # id 是必填字段
        
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
