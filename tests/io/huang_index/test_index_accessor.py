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

# 复杂的嵌套测试模型
class PydanticLocation(BaseModel):
    latitude: float
    longitude: float
    description: Optional[str] = None

class PydanticAddress(BaseModel):
    city: str
    street: str
    location: PydanticLocation
    tags: Dict[str, str]

class PydanticProfile(BaseModel):
    nickname: str
    avatar: str
    preferences: Dict[str, str]

class PydanticUser(BaseModel):
    name: str
    age: int
    addresses: List[PydanticAddress]
    metadata: Dict[str, str]
    profile: PydanticProfile
    friends: List['PydanticUser'] = []  # 自引用嵌套

@dataclass
class DataclassLocation:
    latitude: float
    longitude: float
    description: Optional[str] = None

@dataclass
class DataclassAddress:
    city: str
    street: str
    location: DataclassLocation
    tags: Dict[str, str]

@dataclass
class DataclassProfile:
    nickname: str
    avatar: str
    preferences: Dict[str, str]

@dataclass
class DataclassUser:
    name: str
    age: int
    addresses: List[DataclassAddress]
    metadata: Dict[str, str]
    profile: DataclassProfile
    friends: List['DataclassUser'] = None  # 自引用嵌套

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

    @pytest.fixture
    def complex_pydantic_data(self):
        """复杂Pydantic模型测试数据"""
        friend = PydanticUser(
            name="李四",
            age=25,
            addresses=[
                PydanticAddress(
                    city="深圳",
                    street="科技路",
                    location=PydanticLocation(
                        latitude=22.543096,
                        longitude=114.057865,
                        description="科技园"
                    ),
                    tags={"type": "work"}
                )
            ],
            metadata={"role": "friend"},
            profile=PydanticProfile(
                nickname="小李",
                avatar="avatar2.jpg",
                preferences={"theme": "dark"}
            )
        )
        
        return PydanticUser(
            name="张三",
            age=30,
            addresses=[
                PydanticAddress(
                    city="北京",
                    street="长安街",
                    location=PydanticLocation(
                        latitude=39.909904,
                        longitude=116.397399,
                        description="天安门"
                    ),
                    tags={"type": "home"}
                ),
                PydanticAddress(
                    city="上海",
                    street="南京路",
                    location=PydanticLocation(
                        latitude=31.231706,
                        longitude=121.472644,
                        description="商业区"
                    ),
                    tags={"type": "work"}
                )
            ],
            metadata={"tag": "vip", "level": "1"},
            profile=PydanticProfile(
                nickname="阿三",
                avatar="avatar1.jpg",
                preferences={"theme": "light"}
            ),
            friends=[friend]
        )

    def test_complex_pydantic_access(self, path_parser, composite_accessor, complex_pydantic_data):
        """测试复杂Pydantic模型的访问"""
        test_cases = [
            # 基本属性访问
            ("name", "张三"),
            
            # 嵌套对象属性访问
            ("profile.nickname", "阿三"),
            ("profile.preferences{theme}", "light"),
            
            # 列表中的复杂对象访问
            ("addresses[0].location.latitude", 39.909904),
            ("addresses[0].location.description", "天安门"),
            ("addresses[0].tags{type}", "home"),
            
            # 多层嵌套访问
            ("addresses[1].location.longitude", 121.472644),
            
            # 自引用嵌套访问
            ("friends[0].name", "李四"),
            ("friends[0].profile.nickname", "小李"),
            ("friends[0].addresses[0].location.description", "科技园")
        ]
        
        for path_str, expected in test_cases:
            path = path_parser.parse(path_str)
            value = composite_accessor.get_field_value(complex_pydantic_data, path)
            assert value == expected, f"复杂Pydantic路径 '{path_str}' 访问失败" 