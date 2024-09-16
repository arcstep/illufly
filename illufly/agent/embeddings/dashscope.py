from typing import Any, List
from http import HTTPStatus

import os
from .base import BaseEmbeddings

class DashScopeEmbeddings(BaseEmbeddings):
    """支持最新的阿里云模型服务灵积API的文本向量模型"""

    def __init__(self, model: str=None, api_key: str=None, *args, **kwargs):
        super().__init__(
            model=model or "text-embedding-v2",
            api_key=api_key or os.getenv("DASHSCOPE_API_KEY"),
            *args,
            **kwargs
        )

        try:
            from dashscope import TextEmbedding
            self.client = TextEmbedding(api_key=api_key)
        except ImportError:
            raise RuntimeError(
                "Could not import dashscope package. "
                "Please install it via 'pip install -U dashscope'"
            )


    def call(self, text: str, *args, **kwargs) -> List[float]:
        """
        查询文本向量。
        """
        response = self.client.call(
            model=self.model,
            input=text,
            text_type="query",
            **kwargs
        )
        if response.status_code != HTTPStatus.OK:
            raise Exception('Request id: %s, Status code: %s, error code: %s, error message: %s' % (
                response.request_id, response.status_code,
                response.code, response.message
            ))

        return response.output['embeddings'][0]['embedding']
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        编码文本向量。
        """
        response = self.client.call(
            model=self.model,
            input=texts,
            text_type="document"
        )       
        if response.status_code != HTTPStatus.OK:
            raise Exception('Request id: %s, Status code: %s, error code: %s, error message: %s' % (
                response.request_id, response.status_code,
                response.code, response.message
            ))

        chunks = []
        for chunk in response.output['embeddings']:
            chunks.append(chunk['embedding'])

        return chunks

