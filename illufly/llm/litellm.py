import os
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP", "False")

from typing import Union, List, Optional, Dict, Any
from litellm.caching.caching import Cache
import litellm
import requests
import logging

class LiteLLM():
    """LiteLLM基于OpenAI的API接口，支持多种模型，支持异步请求"""
    def __init__(self, imitator: str=None, provider: str=None, model_type: str="completion", **kwargs):
        """
        provider: 提供者名称，始终使用 OpenAI
        imitator: 如果模型是 OpenAI 兼容接口，可以使用该参数指定使用哪个 imitator
        model_type: 模型类型，"completion" 或 "embedding"
        kwargs: 其他希望填写到 complete 等操作中的参数
        """
        
        # 获取所有可用的 imitators
        self.all_imitators = self._get_all_imitators()
        
        # 设置默认 imitator
        self.imitator = imitator.upper() if imitator and imitator.upper() in self.all_imitators else \
                        self.all_imitators[0] if self.all_imitators else "OPENAI"
        
        # 始终使用 openai 作为 provider
        self.provider = provider or "openai"
        
        # 设置模型类型
        self.model_type = model_type
        
        # 提取缓存相关配置
        self.cache_seed = kwargs.pop("cache_seed", None)  # 用于确定性缓存的种子
        self.force_cache = kwargs.pop("force_cache", False)  # 强制使用缓存
        self.no_cache = kwargs.pop("no_cache", False)  # 禁用缓存
        
        # 获取默认模型
        models = self._get_models_for_imitator(self.imitator, model_type)
        default_model = models[0] if models else None
        
        # 使用传入的模型或默认模型
        model_name = kwargs.pop('model', default_model)
        
        # 如果有模型名称，构建完整模型字符串，使用 openai/model_name 格式
        if model_name:
            model = f"{self.provider}/{model_name}"
        else:
            model = None
        
        self.kwargs = {**kwargs, "model": model}
        
        # 初始化日志
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"初始化 LiteLLM [imitator={self.imitator}, model_type={model_type}, provider={self.provider}]")
        self.logger.info(f"可用imitators: {self.all_imitators}")
        self.logger.info(f"当前imitator可用模型: {models}")

    def _get_all_imitators(self) -> List[str]:
        """从环境变量获取所有配置的imitators"""
        imitators_str = os.getenv("OPENAI_IMITATORS", "OPENAI")
        return [imit.strip().upper() for imit in imitators_str.split(",") if imit.strip()]

    def _get_models_for_imitator(self, imitator: str, model_type: str) -> List[str]:
        """获取指定imitator下特定类型的所有模型"""
        env_key = f"{imitator}_{model_type.upper()}_MODEL"
        models_str = os.getenv(env_key, "")
        return [model.strip() for model in models_str.split(",") if model.strip()]

    def get_imitator_config(self, imitator: str = None) -> Dict[str, Any]:
        """获取指定imitator的配置信息"""
        imitator = imitator.upper() if imitator else self.imitator
        
        return {
            "api_key": os.getenv(f"{imitator}_API_KEY", ""),
            "api_base": os.getenv(f"{imitator}_BASE_URL", ""),
            "completion_models": self._get_models_for_imitator(imitator, "completion"),
            "embedding_models": self._get_models_for_imitator(imitator, "embedding")
        }

    def list_imitators(self) -> List[Dict[str, Any]]:
        """列出所有可用的imitators及其配置"""
        result = []
        for imitator in self.all_imitators:
            config = self.get_imitator_config(imitator)
            # 隐藏API KEY
            if config["api_key"]:
                config["api_key"] = "********"
            result.append({
                "name": imitator,
                **config
            })
        return result

    def get_kwargs(self, imitator: str = None, model_type: str = None, model_index: int = 0, **kwargs) -> Dict[str, Any]:
        """构建API请求参数"""
        # 使用指定的imitator或默认的
        current_imitator = imitator.upper() if imitator else self.imitator
        
        # 使用指定的model_type或默认的
        current_type = model_type or self.model_type
        
        # 获取模型列表
        models = self._get_models_for_imitator(current_imitator, current_type)
        
        # 选择模型名称
        if models and 0 <= model_index < len(models):
            model_name = models[model_index]
        else:
            model_name = kwargs.pop('model', None)
        
        # 构建模型字符串，始终使用 openai/model_name 格式
        if model_name:
            model = f"openai/{model_name}"
        else:
            model = None
        
        # 添加缓存参数
        cache_params = {}
        if self.cache_seed is not None:
            cache_params["cache_seed"] = kwargs.pop("cache_seed", self.cache_seed)
        if self.force_cache:
            cache_params["force_cache"] = kwargs.pop("force_cache", self.force_cache)
        if self.no_cache:
            cache_params["no_cache"] = kwargs.pop("no_cache", self.no_cache)
        
        # 使用当前imitator的API密钥和基础URL
        return {
            "api_key": kwargs.pop("api_key", os.getenv(f"{current_imitator}_API_KEY")),
            "api_base": kwargs.pop("api_base", os.getenv(f"{current_imitator}_BASE_URL")),
            "model": model,
            **cache_params,
            **kwargs
        }

    def completion(self, messages: Union[str, List[Dict[str, Any]]], imitator: str = None, model_index: int = 0, **kwargs) -> Any:
        """对话完成"""
        messages = [{"role": "user", "content": messages}] if isinstance(messages, str) else messages
        request_kwargs = self.get_kwargs(imitator=imitator, model_type="completion", model_index=model_index, **kwargs)
        model = request_kwargs.pop("model")
        
        self.logger.debug(f"使用模型: {model}")
        
        return litellm.completion(
            model=model,
            messages=messages,
            **request_kwargs
        )

    def acompletion(self, messages: Union[str, List[Dict[str, Any]]], imitator: str = None, model_index: int = 0, **kwargs) -> Any:
        """异步对话完成"""
        messages = [{"role": "user", "content": messages}] if isinstance(messages, str) else messages
        request_kwargs = self.get_kwargs(imitator=imitator, model_type="completion", model_index=model_index, **kwargs)
        model = request_kwargs.pop("model")
        
        return litellm.acompletion(
            model=model,
            messages=messages, 
            **request_kwargs
        )
    
    def embedding(self, input: List[str], imitator: str = None, model_index: int = 0, **kwargs) -> Any:
        """文本嵌入"""
        request_kwargs = self.get_kwargs(imitator=imitator, model_type="embedding", model_index=model_index, **kwargs)
        model = request_kwargs.pop("model")
        request_kwargs["input"] = input
        return litellm.embedding(model, **request_kwargs)
    
    def aembedding(self, input: List[str], imitator: str = None, model_index: int = 0, **kwargs) -> Any:
        """异步文本嵌入"""
        request_kwargs = self.get_kwargs(imitator=imitator, model_type="embedding", model_index=model_index, **kwargs)
        model = request_kwargs.pop("model")
        request_kwargs["input"] = input
        return litellm.aembedding(model, **request_kwargs)

def init_litellm(cache_dir: str):
    """初始化litellm配置"""
    # 禁用litellm的不必要网络请求
    litellm.telemetry = False  # 禁用遥测数据收集
    litellm.suppress_debug_info = True  # 抑制调试信息
    
    # 确保缓存目录存在
    if cache_dir and not os.path.exists(cache_dir):
        try:
            os.makedirs(cache_dir, exist_ok=True)
            print(f"已创建LiteLLM缓存目录: {cache_dir}")
        except Exception as e:
            print(f"创建缓存目录失败: {e}")
    
    # 为embedding和多模态操作启用缓存
    if cache_dir:
        litellm.enable_cache(
            type="disk",
            disk_cache_dir=cache_dir,
            supported_call_types=[
                "embedding", "aembedding",  # 文本嵌入
                "transcription", "atranscription",  # 语音转文字
                "image_generation", "aimage_generation",  # 图像生成
                "vision", "avision"  # 多模态视觉
            ]
        )
