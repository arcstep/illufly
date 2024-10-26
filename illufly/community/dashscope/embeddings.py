from typing import Any, List
from http import HTTPStatus

import os
from ...utils import raise_invalid_params
from ...types import BaseEmbeddings

class TextEmbeddings(BaseEmbeddings):
    """支持最新的阿里云模型服务灵积API的文本向量模型"""
    @classmethod
    def allowed_params(cls):
        return {
            "model": "文本嵌入模型的名称",
            "api_key": "API_KEY",
            "output_type": "编码时使用的向量类型",
            **BaseEmbeddings.allowed_params()
        }

    def __init__(self, model: str=None, api_key: str=None, output_type: str="dense", **kwargs):
        raise_invalid_params(kwargs, self.__class__.allowed_params())

        super().__init__(
            model=model or "text-embedding-v3",
            api_key=api_key or os.getenv("DASHSCOPE_API_KEY"),
            dim=kwargs.pop("dim", 1024),
            **kwargs
        )
        self.output_type = output_type

        try:
            import dashscope
        except ImportError:
            raise ImportError(
                "Could not import dashscope package. "
                "Please install it via 'pip install -U dashscope'"
            )

    def query(self, text: str, *args, **kwargs) -> List[float]:
        """
        查询文本向量。
        """
        return self.embed_documents([text], text_type="query", **kwargs)[0]

    def embed_documents(self, texts: List[str], text_type: str="document", **kwargs) -> List[List[float]]:
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
            chunks.append(chunk['embedding'])
            self.dim = len(chunk['embedding'])

        return chunks

