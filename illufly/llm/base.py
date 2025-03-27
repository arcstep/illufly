from typing import Union, List, Optional, Dict, Any
import litellm
from litellm.caching.caching import Cache
import os

class LiteLLM():
    """LiteLLM基于OpenAI的API接口，支持多种模型，支持异步请求"""
    def __init__(self, provider: str=None, imitator: str=None, router_obj=None, **kwargs):
        """
        provider: 提供者名称，用于指定模型，如果不填写就默认为 OpenAI
        imitator: 如果模型是 OpenAI 兼容接口，可以使用该参数简化环境变量导入
        router_obj: 路由对象，可根据策略自动选择多个模型，只有 complete 和 acompletion 支持路由对象
        kwargs: 其他希望填写到 complete 等操作中的参数
        """
        self.provider = (provider or "openai").lower()
        self.imitator = (imitator or provider or "OPENAI").upper()
        self.router_obj = router_obj

        model = f"{self.provider}/{kwargs.pop('model', None)}"
        self.kwargs = {**kwargs, "model": model}

    def get_kwargs(self, **kwargs):
        """重构 litellm 输入参数"""
        return {
            "api_key": kwargs.pop("api_key", os.getenv(f"{self.imitator}_API_KEY")),
            "api_base": kwargs.pop("api_base", os.getenv(f"{self.imitator}_BASE_URL")),
            **self.kwargs,
            **kwargs
        }

    def completion(self, messages: Union[str, List[Dict[str, Any]]], **kwargs) -> Any:
        """对话完成"""
        messages = [{"role": "user", "content": messages}] if isinstance(messages, str) else messages
        if self.router_obj:
            return self.router_obj.completion(messages, **self.get_kwargs(**kwargs))
        else:
            return litellm.completion(messages=messages, **self.get_kwargs(**kwargs))

    def acompletion(self, messages: Union[str, List[Dict[str, Any]]], **kwargs) -> Any:
        """异步对话完成"""
        messages = [{"role": "user", "content": messages}] if isinstance(messages, str) else messages
        if self.router_obj:
            return self.router_obj.acompletion(messages, **self.get_kwargs(**kwargs))
        else:
            return litellm.acompletion(messages=messages, **self.get_kwargs(**kwargs))
    
    def embedding(self, input: List[str], **kwargs) -> Any:
        """文本嵌入"""
        request_kwargs = self.get_kwargs(**kwargs)
        model = request_kwargs.pop("model", None)
        request_kwargs["input"] = input
        return litellm.embedding(model, **request_kwargs)
    
    def aembedding(self, input: List[str], **kwargs) -> Any:
        """异步文本嵌入"""
        request_kwargs = self.get_kwargs(**kwargs)
        model = request_kwargs.pop("model", None)
        request_kwargs["input"] = input
        return litellm.aembedding(model, **request_kwargs)
