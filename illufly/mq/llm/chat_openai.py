import os
from typing import List, Dict, Any, Union
from openai import AsyncOpenAI

from ..service import ServiceDealer
from ..models import TextChunk, TextFinal, ToolCallChunk, ToolCallFinal, StartBlock, UsageBlock

class ChatOpenAI(ServiceDealer):
    DEFAULT_MODELS = {
        "OPENAI": {
            "text": "gpt-4-turbo-preview",
            "vision": "gpt-4-vision-preview"
        },
        "QWEN": {
            "text": "qwen-plus",
            "vision": "qwen-vl-plus"
        },
        "ZHIPU": {
            "text": "glm-4-flash",
            "vision": "glm-4v-flash"
        },
        "DEEPSEEK": {
            "text": "deepseek-chat",
            "vision": "deepseek-chat-v2"
        },
        "MOONSHOT": {
            "text": "moon-shot-chat",
            "vision": "moon-shot-chat-v2"
        }
    }

    PROVIDER_URLS = {
        "QWEN": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "BAIDU": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat",
        "ZHIPU": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "MOONSHOT": "https://api.moonshot.cn/v1",
        "GROQ": "https://api.groq.com/openai/v1",
    }

    def __init__(self, model: str = None, prefix: str = None, extra_args: dict = {}, **kwargs):
        prefix = (prefix or "").upper() or "OPENAI"
        
        # 加载默认模型
        self.text_model = self.DEFAULT_MODELS.get(prefix, {}).get("text", "gpt-4-turbo-preview")
        self.vision_model = self.DEFAULT_MODELS.get(prefix, {}).get("vision", "gpt-4-vision-preview")
        
        # 如果用户指定了模型，优先使用
        self.default_call_args = {
            "model": model,
        }
        self.model_args = {
            "base_url": kwargs.pop("base_url", None) or os.getenv(f"{prefix}_BASE_URL") or self.PROVIDER_URLS.get(prefix),
            "api_key": kwargs.pop("api_key", os.getenv(f"{prefix}_API_KEY")),
            **extra_args
        }
        self.provider = prefix
        self.client = AsyncOpenAI(**self.model_args)

        super().__init__(**kwargs)

    def validate_messages(self, messages: List[Dict[str, Any]]) -> None:
        """验证消息格式，支持简单文本和多模态格式
        Args:
            messages: 消息列表
        Raises:
            ValueError: 当消息格式不正确时
        """
        if not isinstance(messages, list):
            raise ValueError(f"messages 必须是列表类型, 得到 {type(messages)}")
            
        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                raise ValueError(
                    f"每条消息必须是字典格式, 第{i+1}条消息类型为 {type(msg)}"
                )
            
            required_keys = {"role", "content"}
            missing_keys = required_keys - set(msg.keys())
            if missing_keys:
                raise ValueError(
                    f"第{i+1}条消息缺少必要的键: {missing_keys}"
                )
            
            # 验证 role
            if not isinstance(msg["role"], str):
                raise ValueError(
                    f"第{i+1}条消息的 role 必须是字符串, 得到 {type(msg['role'])}"
                )
            
            # 验证 content
            content = msg["content"]
            if isinstance(content, str):
                # 简单文本格式
                pass
            elif isinstance(content, list):
                # 多模态格式
                for idx, item in enumerate(content):
                    if not isinstance(item, dict):
                        raise ValueError(
                            f"第{i+1}条消息的第{idx+1}个内容项必须是字典, 得到 {type(item)}"
                        )
                    if "type" not in item:
                        raise ValueError(
                            f"第{i+1}条消息的第{idx+1}个内容项缺少 type 字段"
                        )
                    if item["type"] == "text":
                        if "text" not in item:
                            raise ValueError(
                                f"第{i+1}条消息的第{idx+1}个文本内容项缺少 text 字段"
                            )
                    elif item["type"] == "image_url":
                        if "image_url" not in item:
                            raise ValueError(
                                f"第{i+1}条消息的第{idx+1}个图片内容项缺少 image_url 字段"
                            )
                    else:
                        raise ValueError(
                            f"第{i+1}条消息的第{idx+1}个内容项包含不支持的 type: {item['type']}"
                        )
            else:
                raise ValueError(
                    f"第{i+1}条消息的 content 必须是字符串或列表, 得到 {type(content)}"
                )

    def _patch_tool_calls(self, delta, current_tool_calls):
        """处理工具调用"""
        for idx, tool_call in enumerate(delta.tool_calls):
            tool_id = tool_call.id
            
            # 如果工具调用不存在，初始化
            if tool_id not in current_tool_calls:
                current_tool_calls[tool_id] = {
                    "id": tool_id,
                    "name": "",  # 初始化为空
                    "arguments": "",
                    "index": idx,
                    "chunks": []
                }
            
            # 更新工具调用信息
            # 只有当函数名称存在且不为空时才更新
            if tool_call.function.name and tool_call.function.name.strip():
                current_tool_calls[tool_id]["name"] = tool_call.function.name
            
            # 更新参数（即使为空也更新，因为可能是有效的空参数）
            if tool_call.function.arguments is not None:
                current_tool_calls[tool_id]["arguments"] += tool_call.function.arguments
            
            # 创建并发送工具调用块
            chunk = ToolCallChunk(
                id=tool_id,
                name=current_tool_calls[tool_id]["name"],  # 使用当前确定的名称
                arguments=tool_call.function.arguments or "",  # 处理可能的None
                index=idx,
                request_id=request_id
            )
            current_tool_calls[tool_id]["chunks"].append(chunk)
            return chunk

    async def _process_vision_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """处理消息，仅在包含图片时转换为多模态格式"""
        processed_messages = []
        
        for msg in messages:
            # 如果已经是多模态格式，直接使用
            if isinstance(msg.get("content"), list):
                processed_messages.append(msg)
                continue
                
            # 处理纯文本消息
            if isinstance(msg.get("content"), str):
                # 检查是否包含图片
                if hasattr(msg, "images") and msg.images:
                    # 转换为多模态格式
                    content_list = [{"type": "text", "text": msg["content"]}]
                    for image in msg.images:
                        image_content = {
                            "type": "image_url",
                            "image_url": {
                                "url": image.url,
                                "detail": getattr(image, "detail", "auto")
                            }
                        }
                        # 处理 base64 图片
                        if hasattr(image, "base64"):
                            image_content["image_url"]["url"] = f"data:image/jpeg;base64,{image.base64}"
                        content_list.append(image_content)
                    processed_messages.append({
                        "role": msg["role"],
                        "content": content_list
                    })
                else:
                    # 不包含图片，保持简单格式
                    processed_messages.append(msg)
            else:
                raise ValueError(f"不支持的 content 类型: {type(msg.get('content'))}")
                
        return processed_messages

    @ServiceDealer.service_method(name="chat", description="Chat with OpenAI")
    async def _chat_openai(
        self,
        messages: Union[List[dict], str],
        **kwargs
    ):
        try:
            if isinstance(messages, str):
                messages = [{"role": "user", "content": messages}]
            
            # 验证消息格式
            self.validate_messages(messages)
            
            # 处理多模态消息
            messages = await self._process_vision_messages(messages)
            
            # 自动选择模型
            if not self.default_call_args['model']:
                # 检查是否包含视觉内容
                has_vision = any(
                    isinstance(msg.get("content"), list) and 
                    any(c.get("type") == "image_url" for c in msg["content"])
                    for msg in messages
                )                
                if has_vision:
                    self.default_call_args["model"] = self.vision_model
                else:
                    self.default_call_args["model"] = self.text_model

            _kwargs = self.default_call_args.copy()
            _kwargs.update({"messages": messages, **kwargs, **{"stream": True}})

            # 开始调用 LLM 接口
            yield StartBlock()
            self._logger.info(f"openai call model: {_kwargs['model']}")
            completion = await self.client.chat.completions.create(**_kwargs)
            
            current_tool_calls = {}

            async for response in completion:
                # self._logger.info(f"openai response: {response}")
                if response.choices:
                    delta = response.choices[0].delta
                    
                    # 处理工具调用
                    if delta.tool_calls:
                        self._logger.info(f"openai tool_calls: {delta.tool_calls}")
                        self._patch_tool_calls(delta, current_tool_calls)
                    
                    # 处理文本内容
                    if delta.content:
                        yield TextChunk(text=delta.content)

                # 处理使用情况
                if hasattr(response, 'usage') and response.usage:
                    usage_data = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens,
                        "model": self.default_call_args["model"],
                        "provider": self.provider
                    }
                    yield UsageBlock(**usage_data)


            # 流结束时处理工具调用
            for tool_data in current_tool_calls.values():
                yield ToolCallFinal(
                    id=tool_data["id"],
                    name=tool_data["name"],
                    arguments=tool_data["arguments"],
                    index=tool_data["index"],
                    chunks=tool_data["chunks"],
                )

        except ValueError as e:
            raise
        except Exception as e:
            raise RuntimeError(f"API 调用失败: {str(e)}")
