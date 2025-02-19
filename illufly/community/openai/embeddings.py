from typing import Any, List
from http import HTTPStatus

import os
from ..base_embeddings import BaseEmbeddings

class OpenAIEmbeddings(BaseEmbeddings):
    """支持最新的OpenAI文本向量模型"""
    def __init__(
        self,
        model: str=None,
        base_url: str=None,
        api_key: str=None,
        dim: int=None,
        extra_args: dict={},
        **kwargs
    ):
        super().__init__(
            model=model or "text-embedding-ada-002",
            base_url=base_url or os.getenv("OPENAI_BASE_URL"),
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            dim=dim or 1536,
            **kwargs
        )
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "Could not import openai package. "
                "Please install it via 'pip install -U openai'"
            )
        
        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key, **extra_args)


    def query(self, text: str,  **kwargs) -> List[float]:
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
            **kwargs
        )
        return [ed.embedding for ed in response.data]

