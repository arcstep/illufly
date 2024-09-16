from typing import Any, List
from http import HTTPStatus

import os
from .base import BaseEmbeddings

class ZhipuEmbeddings(BaseEmbeddings):
    """支持最新的阿里云模型服务灵积API的文本向量模型"""

    def __init__(self, model: str=None, api_key: str=None, *args, **kwargs):
        super().__init__(
            model=model or "embedding-3",
            api_key=api_key or os.getenv("ZHIPUAI_API_KEY"),
            *args,
            **kwargs
        )

        try:
            from zhipuai import ZhipuAI
            self.client = ZhipuAI(api_key=api_key)
        except ImportError:
            raise RuntimeError(
                "Could not import zhipuai package. "
                "Please install it via 'pip install -U zhipuai'"
            )

    def call(self, text: str, *args, **kwargs) -> List[float]:
        """
        查询文本向量。
        """
        response = client.embeddings.create(
            model=self.model,
            input=[text]
        )
        if response.status_code != HTTPStatus.OK:
            raise Exception('Request id: %s, Status code: %s, error code: %s, error message: %s' % (
                response.request_id, response.status_code,
                response.code, response.message
            ))

        return response['data']

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        编码文本向量。
        """
        response = client.embeddings.create(
            model=self.model,
            input=texts
        )
        if response.status_code != HTTPStatus.OK:
            raise Exception('Request id: %s, Status code: %s, error code: %s, error message: %s' % (
                response.request_id, response.status_code,
                response.code, response.message
            ))

        return response['data']

