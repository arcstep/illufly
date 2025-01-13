import os
import json
from typing import List, Dict, Any
from http import HTTPStatus
from ..mq import StreamingService, StreamingBlock
from openai import OpenAI

class ChatOpenAI(StreamingService):
    DEFAULT_MODEL = {
        "OPENAI": "gpt-o1-mini",
        "QWEN": "qwen-plus",
        "BAIDU": "ernie-bot-turbo",
        "ZHIPU": "glm-4-flush",
    }

    def __init__(self, model: str=None, prefix: str=None, extra_args: dict={}, **kwargs):
        """
        使用 imitator 参数指定兼容 OpenAI 接口协议的模型来源，默认 prefix="OPENAI"。
        只需要在环境变量中配置 imitator 对应的 API_KEY 和 BASE_URL 即可。
        
        例如：
        QWEN_API_KEY=sk-...
        QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

        然后使用类似 `ChatOpenAI(prefix="QWEN")` 的代码就可以使用千问系列模型。
        """

        prefix = (prefix or "").upper() or "OPENAI"

        self.default_call_args = {
            "model": model or self.DEFAULT_MODEL.get(prefix, "gpt-o1-mini")
        }
        self.model_args = {
            "base_url": kwargs.pop("base_url", os.getenv(f"{prefix}_BASE_URL")),
            "api_key": kwargs.pop("api_key", os.getenv(f"{prefix}_API_KEY")),
            **extra_args
        }
        self.client = OpenAI(**self.model_args)

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

    async def process(
        self,
        messages: List[dict],
        **kwargs
    ):
        """处理消息流
        Args:
            messages: 消息列表或单个消息字符串
            **kwargs: 其他参数
        Yields:
            StreamingBlock: 流式响应块
        Raises:
            ValueError: 当消息格式不正确时
            RuntimeError: 当连接或处理出错时
        """
        try:
            # 处理单个字符串消息
            if isinstance(messages, str):
                messages = [{"role": "user", "content": messages}]
            
            # 验证消息格式
            self.validate_messages(messages)

            # 构建请求参数
            _kwargs = self.default_call_args.copy()
            _kwargs.update({
                "messages": messages,
                **kwargs,
                **{"stream": True, "stream_options": {"include_usage": True}}
            })

            # 发送请求并处理响应
            completion = self.client.chat.completions.create(**_kwargs)

            usage = {}
            output = []
            request_id = None
            
            for response in completion:
                if response.usage:
                    usage = response.usage
                if response.choices:
                    ai_output = response.choices[0].delta
                    if ai_output.tool_calls:
                        for func in ai_output.tool_calls:
                            func_json = {
                                "id": func.id or "",
                                "type": func.type or "function",
                                "function": {
                                    "name": func.function.name or "",
                                    "arguments": func.function.arguments or ""
                                }
                            }
                            output.append({"tools_call_chunk": func_json})
                            yield StreamingBlock(
                                block_type="tools_call_chunk", 
                                block_content=json.dumps(func_json, ensure_ascii=False)
                            )
                    else:
                        content = ai_output.content
                        if content:
                            output.append({"chunk": content})
                            yield StreamingBlock(
                                block_type="chunk", 
                                block_content=json.dumps(content, ensure_ascii=False)
                            )
            
            # 发送使用情况
            usage_dict = {
                "request_id": request_id,
                "prompt_tokens": usage.prompt_tokens if usage else None,
                "completion_tokens": usage.completion_tokens if usage else None,
                "total_tokens": usage.total_tokens if usage else None
            }
            yield StreamingBlock(
                block_type="usage",
                block_content=json.dumps(usage_dict, ensure_ascii=False)
            )

        except ValueError as e:
            # 格式错误，直接抛出
            raise
        except Exception as e:
            # 其他错误（如连接错误），包装为 RuntimeError
            raise RuntimeError(f"API 调用失败: {str(e)}")
