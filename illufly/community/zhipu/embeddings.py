from typing import Any, List
from http import HTTPStatus

import os
from ...types import BaseEmbeddings

class ZhipuEmbeddings(BaseEmbeddings):
    """支持最新的阿里云模型服务灵积API的文本向量模型"""

    def __init__(self, model: str=None, api_key: str=None, dim: int=None, **kwargs):
        super().__init__(
            model=model or "embedding-3",
            api_key=api_key or os.getenv("ZHIPUAI_API_KEY"),
            dim=kwargs.pop("dim", 2048),
            **kwargs
        )

        try:
            from zhipuai import ZhipuAI
            self.client = ZhipuAI(api_key=api_key)
        except ImportError:
            raise ImportError(
                "Could not import zhipuai package. "
                "Please install it via 'pip install -U zhipuai'"
            )

    def query(self, text: str, **kwargs) -> List[float]:
        """
        查询文本向量。
        """
        return self.embed_documents([text], **kwargs)[0]

    def embed_documents(self, texts: List[str], **kwargs) -> List[List[float]]:
        """
        编码文本向量。
        """
        response = self.client.embeddings.create(
            model=self.model,
            input=texts,
            dimensions=self.dim,
            **kwargs
        )
        return [ed.embedding for ed in response.data]

