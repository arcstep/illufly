import pytest
from typing import List, Dict, Optional
from dataclasses import dataclass
from pydantic import BaseModel

from illufly.io.huang_index.index.accessor import (
    ValueAccessor,
    SequenceAccessor,
    MappingAccessor,
    ModelAccessor,
    DataclassAccessor,
    CompositeAccessor
)
from illufly.io.huang_index.index.path_parser import PathParser

# 测试数据模型
@dataclass
class DataclassAddress:
    city: str
    street: str
    
@dataclass
class DataclassUser:
    name: str
    age: int
    addresses: List[DataclassAddress]
    metadata: Dict[str, str]

class PydanticAddress(BaseModel):
    city: str
    street: str
    
class PydanticUser(BaseModel):
    name: str
    age: int
    addresses: List[PydanticAddress]
    metadata: Dict[str, str]

class TestAccessors:
    @pytest.fixture
    def path_parser(self):
        return PathParser()
    
    @pytest.fixture
    def composite_accessor(self):
        return CompositeAccessor()
    
    @pytest.fixture
    def dict_data(self):
        return {
            "name": "张三",
            "age": 30,
            "addresses": [
                {"city": "北京", "street": "长安街"},
                {"city": "上海", "street": "南京路"}
            ],
            "metadata": {
                "tag": "vip",
                "level": "1"
            }
        }
    
    @pytest.fixture
    def pydantic_data(self):
        """Pydantic模型测试数据"""
        return PydanticUser(
            name="张三",
            age=30,
            addresses=[
                PydanticAddress(city="北京", street="长安街"),
                PydanticAddress(city="上海", street="南京路")
            ],
            metadata={
                "tag": "vip",
                "level": "1"
            }
        )
    
    @pytest.fixture
    def dataclass_data(self):
        """Dataclass测试数据"""
        return DataclassUser(
            name="张三",
            age=30,
            addresses=[
                DataclassAddress(city="北京", street="长安街"),
                DataclassAddress(city="上海", street="南京路")
            ],
            metadata={
                "tag": "vip",
                "level": "1"
            }
        )
    
    def test_sequence_accessor(self, path_parser, dict_data):
        """测试序列访问器"""
        accessor = SequenceAccessor()
        
        # 测试列表索引访问
        path = path_parser.parse("[0]")
        value = accessor.get_field_value(dict_data["addresses"], path)
        assert value == {"city": "北京", "street": "长安街"}
        
        # 测试无效索引
        path = path_parser.parse("[99]")
        value = accessor.get_field_value(dict_data["addresses"], path)
        assert value is None
    
    def test_mapping_accessor(self, path_parser, dict_data):
        """测试映射访问器"""
        accessor = MappingAccessor()
        
        # 测试单层字典访问
        path = path_parser.parse("{name}")
        value = accessor.get_field_value(dict_data, path)
        assert value == "张三"
        
        # 测试嵌套字典访问
        path = path_parser.parse("{metadata}{tag}")
        value = accessor.get_field_value(dict_data, path)
        assert value == "vip"
        
        # 测试无效键
        path = path_parser.parse("{invalid}")
        value = accessor.get_field_value(dict_data, path)
        assert value is None
    
    def test_model_accessor(self, path_parser, pydantic_data):
        """测试Pydantic模型访问器"""
        accessor = ModelAccessor()
        
        # 测试属性访问
        path = path_parser.parse("name")
        value = accessor.get_field_value(pydantic_data, path)
        assert value == "张三"
        
        # 测试嵌套属性访问（属性中的字典）
        path = path_parser.parse("metadata")
        metadata = accessor.get_field_value(pydantic_data, path)
        assert metadata == {"tag": "vip", "level": "1"}
        
        # 测试无效属性
        path = path_parser.parse("invalid")
        value = accessor.get_field_value(pydantic_data, path)
        assert value is None
    
    def test_dataclass_accessor(self, path_parser, dataclass_data):
        """测试Dataclass访问器"""
        accessor = DataclassAccessor()
        
        # 测试属性访问
        path = path_parser.parse("name")
        value = accessor.get_field_value(dataclass_data, path)
        assert value == "张三"
        
        # 测试嵌套属性访问
        path = path_parser.parse("addresses")
        addresses = accessor.get_field_value(dataclass_data, path)
        assert len(addresses) == 2
        assert addresses[0].city == "北京"
    
    def test_composite_accessor_dict(self, path_parser, composite_accessor, dict_data):
        """测试组合访问器处理字典数据"""
        # 测试字典键访问
        path = path_parser.parse("{name}")
        value = composite_accessor.get_field_value(dict_data, path)
        assert value == "张三"
        
        # 测试嵌套字典和列表访问
        path = path_parser.parse("{addresses}[0]{city}")
        value = composite_accessor.get_field_value(dict_data, path)
        assert value == "北京"
        
        # 测试多层字典访问
        path = path_parser.parse("{metadata}{tag}")
        value = composite_accessor.get_field_value(dict_data, path)
        assert value == "vip"
    
    def test_composite_accessor_pydantic(self, path_parser, composite_accessor, pydantic_data):
        """测试组合访问器处理Pydantic模型数据"""
        # 测试属性访问
        path = path_parser.parse("name")
        value = composite_accessor.get_field_value(pydantic_data, path)
        assert value == "张三"
        
        # 测试属性中的列表访问
        path = path_parser.parse("addresses[0].city")
        value = composite_accessor.get_field_value(pydantic_data, path)
        assert value == "北京"
        
        # 测试属性中的字典访问
        path = path_parser.parse("metadata")
        metadata = composite_accessor.get_field_value(pydantic_data, path)
        assert metadata["tag"] == "vip"
    
    def test_complex_paths(self, path_parser, composite_accessor, dict_data):
        """测试复杂路径访问"""
        test_cases = [
            # 字典 -> 列表 -> 字典
            ("{addresses}[0]{city}", "北京"),
            
            # 字典 -> 字典 -> 值
            ("{metadata}{tag}", "vip"),
            
            # 字典 -> 列表 -> 字典 -> 值
            ("{addresses}[1]{street}", "南京路"),
        ]
        
        for path_str, expected in test_cases:
            path = path_parser.parse(path_str)
            value = composite_accessor.get_field_value(dict_data, path)
            assert value == expected, f"路径 '{path_str}' 访问失败" 