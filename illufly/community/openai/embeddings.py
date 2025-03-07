from typing import Any, List
from http import HTTPStatus

import os
from ...rocksdb import IndexedRocksDB
from ..base_embeddings import BaseEmbeddings

class OpenAIEmbeddings(BaseEmbeddings):
    """支持最新的OpenAI文本向量模型"""
    def __init__(
        self,
        model: str=None,
        imitator: str=None,
        base_url: str=None,
        api_key: str=None,
        dim: int=None,
        output_type: str=None,
        max_lines: int=None,
        db: IndexedRocksDB=None,
        extra_args: dict={},
        **kwargs
    ):
        self.imitator = imitator or "OPENAI"
        self.base_url = base_url or os.getenv(f"{self.imitator}_BASE_URL")
        self.api_key = api_key or os.getenv(f"{self.imitator}_API_KEY")
        self.model = model or os.getenv(f"{self.imitator}_MODEL") or "text-embedding-ada-002"

        super().__init__(
            model=self.model,
            dim=dim,
            output_type=output_type or "dense",
            max_lines=max_lines,
            db=db,
            **kwargs
        )
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError(
                "Could not import openai package. "
                "Please install it via 'pip install -U openai'"
            )

        self.client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key, **kwargs)

    async def _embed_texts(self, texts: List[str], **kwargs) -> List[List[float]]:
        """
        编码文本向量。
        """
        response = await self.client.embeddings.create(
            model=self.model,
            input=texts,
            dimensions=self.dim,
            **kwargs
        )
        self.model = response.model
        self.dim = len(response.data[0].embedding)
        return [ed.embedding for ed in response.data]

