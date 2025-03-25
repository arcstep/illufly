from typing import Union, List, Optional, Dict, Any
from litellm import completion

import os
import logging
import asyncio
import time
import httpx

class Chat():
    """OpenAI 对话模型"""

    def __init__(self, imitator: str=None, provider: str=None, **kwargs):
        """
        使用 OpenAI 的 API 接口，需要指定 provider 为 openai 并设置 API_KEY 和 BASE_URL 环境变量。
        """
        self.provider = (provider or "openai").lower()
        self.imitator = (imitator or provider or "OPENAI").upper()
        self.model = kwargs.pop("model", None)
        self.kwargs = kwargs

    def complete(self, messages: List[Dict[str, Any]], model: str=None, **kwargs):
        """
        使用 OpenAI 的 API 接口，需要指定 provider 为 openai 并设置 API_KEY 和 BASE_URL 环境变量。
        """
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        model = model or os.getenv(f"{self.imitator}_MODEL_ID", None)
        self.kwargs["model"] = f"{self.provider}/{model or self.model or 'gpt-4o-mini'}"

        return completion(
            api_key=kwargs.get("api_key", os.getenv(f"{self.imitator}_API_KEY")),
            base_url=kwargs.get("base_url", os.getenv(f"{self.imitator}_BASE_URL")),
            messages=messages,
            **{**self.kwargs, **kwargs}
        )
