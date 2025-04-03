from typing import Union, List, Optional, Dict, Any
from litellm.caching.caching import Cache
import litellm
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
        # 禁用litellm的不必要网络请求
        litellm.telemetry = False  # 禁用遥测数据收集
        litellm.suppress_debug_info = True  # 抑制调试信息
        # 禁用model_cost_map_url的网络请求
        litellm.model_cost_map_url = ""

        self.provider = (provider or "openai").lower()
        self.imitator = (imitator or provider or "OPENAI").upper()
        self.router_obj = router_obj

        # 提取缓存相关配置
        self.cache_seed = kwargs.pop("cache_seed", None)  # 用于确定性缓存的种子
        self.force_cache = kwargs.pop("force_cache", False)  # 强制使用缓存
        self.no_cache = kwargs.pop("no_cache", False)  # 禁用缓存

        model = f"{self.provider}/{kwargs.pop('model', None)}"
        self.kwargs = {**kwargs, "model": model}

    def get_kwargs(self, **kwargs):
        """重构 litellm 输入参数"""
        # 添加缓存相关参数
        cache_params = {}
        if self.cache_seed is not None:
            cache_params["cache_seed"] = kwargs.pop("cache_seed", self.cache_seed)
        if self.force_cache:
            cache_params["force_cache"] = kwargs.pop("force_cache", self.force_cache)
        if self.no_cache:
            cache_params["no_cache"] = kwargs.pop("no_cache", self.no_cache)

        return {
            "api_key": kwargs.pop("api_key", os.getenv(f"{self.imitator}_API_KEY")),
            "api_base": kwargs.pop("api_base", os.getenv(f"{self.imitator}_BASE_URL")),
            **self.kwargs,
            **cache_params,
            **kwargs
        }

    def completion(self, messages: Union[str, List[Dict[str, Any]]], **kwargs) -> Any:
        """对话完成"""
        messages = [{"role": "user", "content": messages}] if isinstance(messages, str) else messages
        model = self.get_kwargs(**kwargs).get("model")
        
        if self.router_obj:
            return self.router_obj.completion(
                messages=messages,
                **self.get_kwargs(**kwargs)
            )
        else:
            return litellm.completion(
                model=model,
                messages=messages,
                **{k: v for k, v in self.get_kwargs(**kwargs).items() if k != "model"}
            )

    def acompletion(self, messages: Union[str, List[Dict[str, Any]]], **kwargs) -> Any:
        """异步对话完成"""
        messages = [{"role": "user", "content": messages}] if isinstance(messages, str) else messages
        model = self.get_kwargs(**kwargs).get("model")
        
        if self.router_obj:
            return self.router_obj.acompletion(
                messages=messages, 
                **self.get_kwargs(**kwargs)
            )
        else:
            return litellm.acompletion(
                model=model,
                messages=messages, 
                **{k: v for k, v in self.get_kwargs(**kwargs).items() if k != "model"}
            )
    
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
