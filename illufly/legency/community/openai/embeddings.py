from typing import Any, List
from http import HTTPStatus

import os
from voidring import IndexedRocksDB
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
        timeout: int = 30,
        max_retries: int = 3,
        **kwargs
    ):
        self.imitator = imitator or "OPENAI"
        self.base_url = base_url or os.getenv(f"{self.imitator}_BASE_URL")
        self.api_key = api_key or os.getenv(f"{self.imitator}_API_KEY")
        self.model = model or os.getenv(f"{self.imitator}_MODEL") or "text-embedding-ada-002"
        self.max_retries = max_retries
        self.timeout = timeout
        max_lines = max_lines or 3

        super().__init__(
            model=self.model,
            dim=dim,
            output_type=output_type or "dense",
            max_lines=max_lines,
            db=db,
            **kwargs
        )
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "Could not import openai package. "
                "Please install it via 'pip install -U openai'"
            )

        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout,
            max_retries=self.max_retries,
            **kwargs
        )

    async def _embed_texts(self, texts: List[str], **kwargs) -> List[List[float]]:
        """
        编码文本向量。
        """
        from tenacity import (
            retry,
            retry_if_exception_type,
            stop_after_attempt,
            wait_exponential
        )
        from openai import APITimeoutError, APIError

        @retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((APITimeoutError, APIError)),
            reraise=True
        )
        async def embed_with_retry():
            response = await self.client.embeddings.create(
                model=self.model,
                input=texts,
                **kwargs
            )
            return response

        try:
            response = await embed_with_retry()
            self.model = response.model
            self.dim = len(response.data[0].embedding)
            return [ed.embedding for ed in response.data]
        except Exception as e:
            self._logger.error(f"嵌入失败: {str(e)} (已尝试{self.max_retries}次)")
            raise

    def _sync_embed_texts(self, texts: List[str], **kwargs) -> List[List[float]]:
        """
        编码文本向量。
        """
        from tenacity import (
            retry,
            retry_if_exception_type,
            stop_after_attempt,
            wait_exponential
        )
        from openai import APITimeoutError, APIError

        @retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((APITimeoutError, APIError)),
            reraise=True
        )
        def embed_with_retry():
            response = self.client.embeddings.create(
                model=self.model,
                input=texts,
                **kwargs
            )
            return response

        try:
            response = embed_with_retry()
            self.model = response.model
            self.dim = len(response.data[0].embedding)
            return [ed.embedding for ed in response.data]
        except Exception as e:
            self._logger.error(f"嵌入失败: {str(e)} (已尝试{self.max_retries}次)")
            raise
