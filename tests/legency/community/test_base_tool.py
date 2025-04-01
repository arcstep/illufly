import pytest
from datetime import datetime
from typing import Dict, Any, Optional, Annotated, List, Literal
from pydantic import Field, BaseModel
from illufly.community.base_tool import BaseTool, is_json_serializable
from illufly.community.models import TextFinal
from deepdiff import DeepDiff

@pytest.mark.parametrize("type_hint, expected", [
    (str, True),
    (Annotated[int, Field(gt=0)], True),
    (List[Annotated[str, Field(max_length=10)]], True),
    (Dict[str, Annotated[float, Field(ge=0)]], True),
    (datetime, False),
    (Dict[int, str], True),
    (List[bytes], False),
])
def test_is_json_serializable(type_hint, expected):
    assert is_json_serializable(type_hint) == expected

@pytest.mark.asyncio
async def test_define_tools():
    """测试工具定义场景"""
    class WeatherTool(BaseTool):
        name = "get_weather"
        description = "获取指定城市的天气信息"

        @classmethod
        def get_parameters(cls) -> Dict[str, tuple]:
            return {
                "location": (str, "城市名称，例如：杭州市")
            }

        @classmethod
        async def call(cls, location: str):
            yield TextFinal(text=f"{location}天气：24℃")

    # 验证生成的OpenAI工具描述
    assert WeatherTool.to_openai() == {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取指定城市的天气信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "城市名称，例如：杭州市"
                    }
                },
                "required": ["location"]
            }
        }
    }

def assert_tool_schema(tool_cls, expected):
    schema = tool_cls.to_openai()["function"]["parameters"]
    diff = DeepDiff(schema, expected, ignore_order=True)
    assert not diff, f"Schema差异：\n{diff.pretty()}"

@pytest.mark.asyncio
async def test_parameter_modes_1():
    """
    测试三种参数定义方式
    方式1：显式BaseModel
    """
    class ExplicitArgs(BaseModel):
        count: int = Field(..., description="数量")
        enabled: bool = Field(False, description="是否启用")

    class ExplicitModelTool(BaseTool):
        name = "explicit_tool"
        description = "显式模型工具"
        args_schema = ExplicitArgs

        @classmethod
        async def call(cls, count: int, enabled: bool):
            yield TextFinal(text=f"Count: {count}, Enabled: {enabled}")

    assert_tool_schema(ExplicitModelTool, {
        "type": "object",
        "properties": {
            "count": {
                "type": "integer", 
                "description": "数量"
            },
            "enabled": {
                "type": "boolean",
                "description": "是否启用"
            }
        },
        "required": ["count"]
    })

@pytest.mark.asyncio
async def test_parameter_modes_2():
    """
    测试三种参数定义方式
    方式2：使用get_parameters
    """    
    class GetParamsTool(BaseTool):
        name = "get_params_tool"
        description = "参数定义工具"
        
        @classmethod
        def get_parameters(cls):
            return {
                "location": (str, "城市名称"),
                "count": (Annotated[int, Field(gt=0)], "正数数量", 1)
            }

        @classmethod
        async def call(cls, location: str, count: int):
            yield TextFinal(text=f"Location: {location}, Count: {count}")

    assert_tool_schema(GetParamsTool, {
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "城市名称"},
            "count": {"type": "integer", "description": "正数数量"}
        },
        "required": ["location"]
    })

@pytest.mark.asyncio
async def test_parameter_modes_3():
    """
    测试三种参数定义方式
    方式3：推断call签名
    """
    class InferredTool(BaseTool):
        name = "inferred_tool"
        description = "推断参数工具"
        
        @classmethod
        async def call(
            cls,
            user_id: Annotated[int, Field(description="用户ID")],
            active: bool = False
        ):
            yield TextFinal(text=f"User {user_id} active: {active}")

    assert_tool_schema(InferredTool, {
        "type": "object",
        "properties": {
            "user_id": {"type": "integer", "description": "用户ID"},
            "active": {"type": "boolean", "description": "无描述"}
        },
        "required": ["user_id"]
    })

@pytest.mark.asyncio
async def test_invalid_types():
    # 测试非法类型
    with pytest.raises(TypeError):
        class InvalidTypeTool(BaseTool):
            name = "invalid_tool"
            description = "非法类型工具"
            
            @classmethod
            async def call(cls, dt: datetime):
                yield TextFinal(text=str(dt))
        InvalidTypeTool.to_openai()
