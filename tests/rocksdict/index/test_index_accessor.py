import pytest
from typing import List, Dict, Optional
from dataclasses import dataclass
from pydantic import BaseModel

from illufly.rocksdict.index.accessor import (
    ValueAccessor,
    SequenceAccessor,
    MappingAccessor,
    ModelAccessor,
    CompositeAccessor
)
from illufly.rocksdict.index.path_parser import PathParser

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

    @property
    def mykey(self):
        return f"{self.name}_{self.age}"


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
                PydanticAddress(
                    city="北京", 
                    street="长安街",
                    location=PydanticLocation(
                        latitude=39.909904,
                        longitude=116.397399
                    ),
                    tags={"type": "home"}
                ),
                PydanticAddress(
                    city="上海", 
                    street="南京路",
                    location=PydanticLocation(
                        latitude=31.231706,
                        longitude=121.472644
                    ),
                    tags={"type": "work"}
                )
            ],
            metadata={
                "tag": "vip",
                "level": "1"
            },
            profile=PydanticProfile(
                nickname="阿三",
                avatar="avatar.jpg",
                preferences={"theme": "light"}
            )
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

        # 测试属性索引
        path = path_parser.parse("mykey")
        value = accessor.get_field_value(pydantic_data, path)
        assert value == "张三_30"
    
    
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

    def test_sequence_accessor_validation(self, path_parser):
        """测试序列访问器的路径验证"""
        accessor = SequenceAccessor()
        
        # 测试有效路径
        path = path_parser.parse("[0]")
        assert accessor.validate_path(List[str], path) is None
        
        # 测试无效路径类型
        path = path_parser.parse("name")
        error = accessor.validate_path(List[str], path)
        assert error is not None
        assert "不支持 ATTRIBUTE 访问" in error
        
    def test_mapping_accessor_validation(self, path_parser):
        """测试映射访问器的路径验证"""
        accessor = MappingAccessor()
        
        # 测试有效路径 - 花括号访问
        path = path_parser.parse("{key}")
        assert accessor.validate_path(Dict[str, str], path) is None
        
        # 测试有效路径 - 属性访问
        path = path_parser.parse("key")
        assert accessor.validate_path(Dict[str, str], path) is None
        
        # 测试无效路径类型
        path = path_parser.parse("[0]")
        error = accessor.validate_path(Dict[str, str], path)
        assert error is not None
        assert "不支持 SEQUENCE 访问" in error

    def test_model_accessor_validation(self, path_parser):
        """测试Pydantic模型访问器的路径验证"""
        accessor = ModelAccessor()
        
        # 测试有效路径
        path = path_parser.parse("name")
        assert accessor.validate_path(PydanticUser, path) is None
        
        # 测试无效字段
        path = path_parser.parse("invalid_field")
        error = accessor.validate_path(PydanticUser, path)
        assert error is not None
        assert "没有字段" in error
        
        # 测试无效访问类型
        path = path_parser.parse("[0]")
        error = accessor.validate_path(PydanticUser, path)
        assert error is not None
        assert "不支持 SEQUENCE 访问" in error
        
        # 测试非Pydantic类型
        path = path_parser.parse("name")
        error = accessor.validate_path(dict, path)
        assert error is not None
        assert "不是 Pydantic 模型" in error

    def test_composite_accessor_validation(self, path_parser):
        """测试组合访问器的路径验证"""
        accessor = CompositeAccessor(logger)
        
        # 测试Pydantic模型的复杂路径
        test_cases = [
            # 有效路径
            ("name", PydanticUser, None),
            ("addresses[0].city", PydanticUser, None),
            ("profile.preferences{theme}", PydanticUser, None),
            ("metadata{tag}", PydanticUser, None),
            
            # 无效路径
            ("invalid_field", PydanticUser, "没有字段"),
            ("addresses{key}", PydanticUser, "不支持 MAPPING 访问"),
            ("profile[0]", PydanticUser, "不支持 SEQUENCE 访问"),
            
            # 嵌套路径验证
            ("addresses[0].invalid", PydanticUser, "没有字段"),
            ("profile.preferences[0]", PydanticUser, "不支持 SEQUENCE 访问"),
        ]
        
        for path_str, value_type, expected_error in test_cases:
            path = path_parser.parse(path_str)
            error = accessor.validate_path(value_type, path)
            
            if expected_error is None:
                assert error is None, f"路径 '{path_str}' 应该有效"
            else:
                assert error is not None, f"路径 '{path_str}' 应该无效"
                assert expected_error in error, f"错误消息应包含 '{expected_error}'"


    def test_accessor_registry_validation(self):
        """测试访问器注册表的路径验证"""
        from illufly.rocksdict.index.accessor import AccessorRegistry
        registry = AccessorRegistry()
        
        # 测试有效路径
        registry.validate_path(PydanticUser, "name")  # 不应抛出异常
        registry.validate_path(PydanticUser, "addresses[0].city")  # 不应抛出异常
        
        # 测试无效路径
        with pytest.raises(ValueError) as exc:
            registry.validate_path(PydanticUser, "invalid_field")
        assert "无效的访问路径" in str(exc.value)
        
        with pytest.raises(ValueError) as exc:
            registry.validate_path(PydanticUser, "addresses{key}")
        assert "无效的访问路径" in str(exc.value) 

    def test_model_accessor_can_handle(self):
        """测试Pydantic模型访问器的类型处理"""
        accessor = ModelAccessor()
        
        # 测试类型
        assert accessor.can_handle(PydanticUser) is True
        assert accessor.can_handle(dict) is False
        
        # 测试实例 - 提供所有必需字段
        user = PydanticUser(
            name="test",
            age=1,
            addresses=[
                PydanticAddress(
                    city="北京",
                    street="长安街",
                    location=PydanticLocation(
                        latitude=39.9,
                        longitude=116.3
                    ),
                    tags={"type": "home"}
                )
            ],
            metadata={"key": "value"},
            profile=PydanticProfile(
                nickname="test",
                avatar="avatar.jpg",
                preferences={"theme": "dark"}
            )
        )
        assert accessor.can_handle(user) is True
        assert accessor.can_handle({"name": "test"}) is False

    def test_sequence_accessor_can_handle(self):
        """测试序列访问器的类型处理"""
        accessor = SequenceAccessor()
        
        # 测试泛型类型
        assert accessor.can_handle(List[str]) is True
        assert accessor.can_handle(List[PydanticUser]) is True
        
        # 测试普通类型
        assert accessor.can_handle(list) is True
        assert accessor.can_handle(str) is False
        
        # 测试实例
        assert accessor.can_handle([1, 2, 3]) is True
        assert accessor.can_handle("123") is False

    def test_mapping_accessor_can_handle(self):
        """测试映射访问器的类型处理"""
        accessor = MappingAccessor()
        
        # 测试泛型类型
        assert accessor.can_handle(Dict[str, str]) is True
        assert accessor.can_handle(Dict[str, PydanticUser]) is True
        
        # 测试普通类型
        assert accessor.can_handle(dict) is True
        assert accessor.can_handle(list) is False
        
        # 测试实例
        assert accessor.can_handle({"key": "value"}) is True
        assert accessor.can_handle([1, 2, 3]) is False 