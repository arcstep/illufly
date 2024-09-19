from typing import Any, List
from http import HTTPStatus

import os
from ...types import BaseEmbeddings

class DashScopeEmbeddings(BaseEmbeddings):
    """支持最新的阿里云模型服务灵积API的文本向量模型"""

    def __init__(self, model: str=None, api_key: str=None, output_type: str="dense", *args, **kwargs):
        super().__init__(
            model=model or "text-embedding-v3",
            api_key=api_key or os.getenv("DASHSCOPE_API_KEY"),
            *args,
            **kwargs
        )
        self.output_type = output_type

        try:
            import dashscope
        except ImportError:
            raise RuntimeError(
                "Could not import dashscope package. "
                "Please install it via 'pip install -U dashscope'"
            )

    def query(self, text: str, *args, **kwargs) -> List[float]:
        """
        查询文本向量。
        """
        return self.embed_documents([text], text_type="query")[0]

    def embed_documents(self, texts: List[str], text_type: str="document") -> List[List[float]]:
        """
        编码文本向量。
        """
        import dashscope
        dashscope.api_key = self.api_key
        from dashscope import TextEmbedding

        response = TextEmbedding.call(
            model=self.model,
            input=texts,
            text_type=text_type,
            dimension=self.dim,
            output_type=self.output_type
        )
        if response.status_code != HTTPStatus.OK:
            raise Exception('Request id: %s, Status code: %s, error code: %s, error message: %s' % (
                response.request_id, response.status_code,
                response.code, response.message
            ))

        chunks = []
        for chunk in response.output['embeddings']:
            chunks.append(chunk['embedding'])
            self.dim = len(chunk['embedding'])

        return chunks

