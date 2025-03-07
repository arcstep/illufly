from typing import Any, List
from http import HTTPStatus

import os
from ..base_embeddings import BaseEmbeddings

class TextEmbeddings(BaseEmbeddings):
    """支持最新的阿里云模型服务灵积API的文本向量模型"""

    def __init__(self, model: str=None, api_key: str=None, output_type: str=None, **kwargs):
        super().__init__(
            model=model or "text-embedding-v3",
            api_key=api_key or os.getenv("DASHSCOPE_API_KEY"),
            dim=kwargs.pop("dim", 1024),
            **kwargs
        )
        self.output_type = output_type or "dense"

        try:
            import dashscope
            dashscope.api_key = self.api_key
            from dashscope import TextEmbedding
            self.client = TextEmbedding
        except ImportError:
            raise ImportError(
                "Could not import dashscope package. "
                "Please install it via 'pip install -U dashscope'"
            )

    def _embed_texts(self, texts: List[str], **kwargs) -> List[List[float]]:
        """
        编码文本向量。
        """
        response = self.client.call(
            model=self.model,
            input=texts,
            dimension=self.dim,
            output_type=self.output_type,
            **kwargs
        )
        if response.status_code != HTTPStatus.OK:
            raise Exception('Request id: %s, Status code: %s, error code: %s, error message: %s' % (
                response.request_id, response.status_code,
                response.code, response.message
            ))

        chunks = []
        for chunk in response.output['embeddings']:
            self.dim = len(chunk['embedding'])
            chunks.append(chunk['embedding'])

        return chunks

