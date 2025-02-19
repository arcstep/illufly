import pytest
from typing import Dict, Any
from pydantic import Field
from illufly.community.base_tool import BaseTool, ToolCallMessage

@pytest.mark.asyncio
async def test_define_tools():
    """测试工具定义场景"""
    class WeatherTool(BaseTool):
        name = "get_weather"
        description = "获取指定城市的天气信息"

        @classmethod
        def get_parameters(cls) -> Dict[str, Any]:
            """获取参数结构（子类可覆盖）"""
            return {
                "location": Field(description="城市名称，例如：杭州市")
            }

        @classmethod
        async def call(self, location: str):
            yield ToolCallMessage(
                text=f"{location}天气：24℃",
            )
    
    target_test_tools = [
        {
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
    ]

    assert WeatherTool.to_openai_tool() == target_test_tools[0]
