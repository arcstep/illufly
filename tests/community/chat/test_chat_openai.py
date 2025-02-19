import pytest
import json

import logging
from illufly.community.openai import ChatOpenAI
from illufly.mq.models import BlockType, ToolCallChunk, ToolCallFinal, TextChunk, TextFinal
from illufly.community.base_tool import BaseTool, ToolCallMessage

logger = logging.getLogger(__name__)

@pytest.fixture
async def chat_service():
    """ChatFake 服务实例"""
    service = ChatOpenAI(
        model="glm-4-flash",
        imitator="ZHIPU",
    )
    return service

@pytest.fixture
def mock_tool():
    """模拟工具类"""
    class GetWeather(BaseTool):
        name = "get_weather"
        description = "获取天气信息"
        
        @classmethod
        async def call(cls, city: str):
            yield ToolCallMessage(text=f"{city} 的天气是晴天")
    
    return GetWeather()

@pytest.mark.asyncio
async def test_chat_basic(chat_service):
    """测试基本聊天功能"""
    # 发送请求并收集响应
    chunks = []
    final_text = ""
    async for chunk in chat_service.generate(messages=[{"role": "user", "content": "请跟我重复一遍：我很棒"}]):
        logger.info(f"[{chunk.block_type}] {chunk.content}")
        chunks.append(chunk)
        if chunk.block_type == BlockType.TEXT_FINAL:
            final_text = chunk.content    
    # 验证响应
    assert len(chunks) > 0, "应该收到响应"
    assert "我很棒" in final_text, "响应内容应该匹配预设"

@pytest.mark.asyncio
async def test_tool_calls(chat_service: ChatOpenAI, mock_tool: BaseTool):
    """测试完整的工具调用流程"""
    # 初始消息（必须包含足够上下文）
    messages = [{
        "role": "user",
        "content": "请帮我看看明天广州的天气"
    }]
    
    # 第一阶段：获取工具调用请求
    assistant_messages = []
    tool_calls = []
    async for chunk in chat_service.generate(messages, tools=[mock_tool]):
        if isinstance(chunk, ToolCallFinal):
            tool_calls.append(chunk)
        if isinstance(chunk, TextChunk):
            # 收集assistant的文本响应（如果有）
            assistant_messages.append(chunk.text)
    
    # 必须将assistant的响应添加到消息历史
    if assistant_messages:
        messages.append({
            "role": "assistant",
            "content": "".join(assistant_messages)
        })
    if tool_calls:
        messages.append({
            "role": "assistant",
            "tool_calls": [{
                "id": tc.tool_call_id,
                "type": "function",
                "function": {
                    "name": tc.tool_name,
                    "arguments": tc.arguments
                }
            } for tc in tool_calls]
        })
    
    # 执行工具调用
    tool_responses = []
    for tc in tool_calls:
        async for resp in mock_tool.call(city=json.loads(tc.arguments)["city"]):
            if isinstance(resp, ToolCallMessage):
                tool_responses.append({
                    "tool_call_id": tc.tool_call_id,
                    "content": resp.text
                })
    
    # 添加工具响应到消息历史（必须包含对应的tool_call_id）
    for resp in tool_responses:
        messages.append({
            "role": "tool",
            "tool_call_id": resp["tool_call_id"],
            "content": resp["content"]
        })
    
    # 第二阶段：处理工具结果
    final_text = ""
    async for chunk in chat_service.generate(messages):
        if isinstance(chunk, TextFinal):
            final_text = chunk.text
    
    # 验证最终回复包含处理结果
    assert "晴天" in final_text, "应正确处理工具返回结果"

@pytest.mark.asyncio
async def test_tool_calls_quickly(chat_service: ChatOpenAI, mock_tool: BaseTool):
    """测试完整的工具调用流程"""
    # 初始消息（必须包含足够上下文）
    messages = [{
        "role": "user",
        "content": "请帮我确认明天广州是否适合晒被子"
    }]
    
    final_text = ""
    async for chunk in chat_service.chat(messages, tools=[mock_tool]):
        logger.info(f"[{chunk.block_type}] {chunk.content}")
        if isinstance(chunk, TextFinal):
            final_text = chunk.content
    
    # 验证最终回复包含处理结果
    assert "晴天" in final_text, "应正确处理工具返回结果"

@pytest.mark.asyncio
async def test_tool_without_parameters(chat_service: ChatOpenAI):
    """测试无参数工具调用"""
    class NoParamTool(BaseTool):
        name = "no_param_tool"
        description = "无参数测试工具"
        
        @classmethod
        async def call(cls):
            yield ToolCallMessage(text="无参数调用成功")

    # 执行调用
    messages = [{"role": "user", "content": "请直接调用no_param_tool"}]
    tool_calls = []
    async for chunk in chat_service.chat(messages, tools=[NoParamTool()]):
        logger.info(f"[{chunk.block_type}] {chunk.content}")
        if isinstance(chunk, ToolCallFinal):
            tool_calls.append(chunk)
    
    # 验证工具调用
    assert len(tool_calls) == 1, "应触发工具调用"
    args = json.loads(tool_calls[0].arguments)
    assert args == {}, "参数应为空字典"
    
    # 验证工具执行
    async for resp in NoParamTool.call():
        assert "成功" in resp.text

@pytest.mark.asyncio
async def test_tool_with_multiple_parameters(chat_service: ChatOpenAI):
    """测试多类型参数工具调用"""
    class MultiTypeTool(BaseTool):
        name = "multi_type_tool"
        description = "多类型参数测试工具"
        
        @classmethod
        async def call(cls, text: str, count: int, ratio: float, active: bool):
            yield ToolCallMessage(text=f"{text}|{count}|{ratio}|{active}")

    # 构造测试参数
    test_params = {
        "text": "测试文本",
        "count": 5,
        "ratio": 3.14,
        "active": True
    }
    prompt = f"调用multi_type_tool工具，参数：{json.dumps(test_params, ensure_ascii=False)}"
    
    # 执行调用
    messages = [{"role": "user", "content": prompt}]
    tool_calls = []
    async for chunk in chat_service.chat(messages, tools=[MultiTypeTool()]):
        logger.info(f"[{chunk.block_type}] {chunk.content}")
        if isinstance(chunk, ToolCallFinal):
            tool_calls.append(chunk)
    
    # 验证参数解析
    assert len(tool_calls) == 1, "应触发工具调用"
    args = json.loads(tool_calls[0].arguments)
    assert args == test_params, "参数应完全匹配"
    
    # 验证类型转换
    assert isinstance(args["count"], int), "整型参数应正确转换"
    assert isinstance(args["ratio"], float), "浮点型参数应正确转换"
    assert isinstance(args["active"], bool), "布尔型参数应正确转换"

@pytest.mark.asyncio
async def test_tool_with_complex_parameters(chat_service: ChatOpenAI):
    """测试复杂结构参数工具调用"""
    class ComplexParamTool(BaseTool):
        name = "complex_tool"
        description = "复杂参数测试工具"
        
        @classmethod
        async def call(cls, data: dict):
            yield ToolCallMessage(text=json.dumps(data, ensure_ascii=False))

    # 构造复杂参数
    complex_data = {
        "users": [
            {"id": 1, "name": "张三", "scores": [85.5, 90.0]},
            {"id": 2, "name": "李四", "active": True}
        ],
        "meta": {
            "page": 1,
            "total": 100,
            "tags": ["重要", "测试"]
        }
    }
    prompt = f"调用complex_tool工具，参数为：{json.dumps(complex_data, ensure_ascii=False)}"
    
    # 执行调用
    messages = [{"role": "user", "content": prompt}]
    tool_calls = []
    async for chunk in chat_service.chat(messages, tools=[ComplexParamTool()]):
        logger.info(f"[{chunk.block_type}] {chunk.content}")
        if isinstance(chunk, ToolCallFinal):
            tool_calls.append(chunk)
    
    # 验证参数结构
    assert len(tool_calls) == 1, "应触发工具调用"
    received_data = json.loads(tool_calls[0].arguments)["data"]
    assert received_data == complex_data, "复杂结构应完整传递"
    
    # 验证深层结构
    assert isinstance(received_data["users"][0]["scores"], list), "嵌套列表应保持类型"
    assert received_data["meta"]["tags"] == ["重要", "测试"], "数组元素应正确"
