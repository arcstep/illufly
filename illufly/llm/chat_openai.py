import os
from typing import List, Dict, Any, Union
from ..mq import Publisher, StreamingBlock, BlockType
from ..base import SimpleService, CallContext, call_with_cache
from openai import AsyncOpenAI

class ChatOpenAI(SimpleService):
    DEFAULT_MODEL = {
        "OPENAI": "gpt-4-vision-preview",
        "QWEN": "qwen-vl-plus",
        "BAIDU": "ernie-bot-4",
        "ZHIPU": "glm-4v",
        "MOONSHOT": "moonshot-v1-8k",
        "GROQ": "mixtral-8x7b-32768",
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
        
        # 设置默认模型和基础URL
        model = model or self.DEFAULT_MODEL.get(prefix, "gpt-4-turbo-preview")
        base_url = kwargs.pop("base_url", None) or os.getenv(f"{prefix}_BASE_URL") or self.PROVIDER_URLS.get(prefix)
        
        self.default_call_args = {
            "model": model,
        }
        self.model_args = {
            "base_url": base_url,
            "api_key": kwargs.pop("api_key", os.getenv(f"{prefix}_API_KEY")),
            **extra_args
        }
        self.provider = prefix
        self.client = AsyncOpenAI(**self.model_args)

        super().__init__(**kwargs)

    def validate_messages(self, messages: List[Dict[str, Any]]) -> None:
        """验证消息格式
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
            
            if not isinstance(msg["role"], str):
                raise ValueError(
                    f"第{i+1}条消息的 role 必须是字符串, 得到 {type(msg['role'])}"
                )
            
            if not isinstance(msg["content"], str):
                raise ValueError(
                    f"第{i+1}条消息的 content 必须是字符串, 得到 {type(msg['content'])}"
                )

    async def _process_vision_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """处理包含视觉内容的消息"""
        processed_messages = []
        for msg in messages:
            if isinstance(msg.get("content"), list):
                # 处理多模态内容
                content_list = []
                for content in msg["content"]:
                    if content.get("type") == "text":
                        content_list.append({"type": "text", "text": content["text"]})
                    elif content.get("type") == "image":
                        image_content = {
                            "type": "image",
                            "image_url": content.get("image_url"),
                            "detail": content.get("detail", "auto")
                        }
                        # 处理 base64 图片
                        if content.get("image_base64"):
                            image_content["image_url"] = f"data:image/jpeg;base64,{content['image_base64']}"
                        content_list.append(image_content)
                processed_messages.append({
                    "role": msg["role"],
                    "content": content_list
                })
            else:
                processed_messages.append(msg)
        return processed_messages

    async def _async_handler(
        self,
        messages: Union[List[dict], str],
        thread_id: str,
        publisher: Publisher,
        **kwargs
    ):
        try:
            if isinstance(messages, str):
                messages = [{"role": "user", "content": messages}]
            
            # 验证消息格式
            self.validate_messages(messages)
            
            # 处理多模态消息
            messages = await self._process_vision_messages(messages)
            
            # 检查是否包含视觉内容
            has_vision = any(
                isinstance(msg.get("content"), list) and 
                any(c.get("type") == "image" for c in msg["content"])
                for msg in messages
            )
            
            # 如果包含视觉内容，确保使用支持视觉的模型
            if has_vision and "vision" not in self.default_call_args["model"]:
                vision_model = self.DEFAULT_MODEL.get(self.provider, "").replace("-plus", "-vision")
                if vision_model:
                    self.default_call_args["model"] = vision_model

            _kwargs = self.default_call_args.copy()
            _kwargs.update({
                "messages": messages,
                **kwargs,
                **{"stream": True}
            })

            # 发送开始标记
            publisher.publish(thread_id, StreamingBlock.create_start(thread_id))

            completion = await self.client.chat.completions.create(**_kwargs)
            
            async for response in completion:
                self._logger.info(f"openai response: {response}")
                if response.choices:
                    delta = response.choices[0].delta
                    
                    # 处理工具调用
                    if delta.tool_calls:
                        for tool_call in delta.tool_calls:
                            tool_data = {
                                "id": tool_call.id,
                                "type": tool_call.type,
                                "function": {
                                    "name": tool_call.function.name,
                                    "arguments": tool_call.function.arguments
                                }
                            }
                            publisher.publish(
                                thread_id,
                                StreamingBlock.create_tools_call(tool_data, thread_id)
                            )
                    
                    # 处理文本内容
                    if delta.content:
                        publisher.publish(
                            thread_id,
                            StreamingBlock.create_chunk(delta.content, thread_id)
                        )

                # 处理使用情况
                if hasattr(response, 'usage') and response.usage:
                    usage_data = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens,
                        "model": self.default_call_args["model"],
                        "provider": self.provider
                    }
                    publisher.publish(
                        thread_id,
                        StreamingBlock.create_usage(usage_data, thread_id)
                    )

        except ValueError as e:
            raise
        except Exception as e:
            raise RuntimeError(f"API 调用失败: {str(e)}")
