from typing import List

import os
from ...types import BaseEmbeddings
from ...utils import raise_invalid_params

class HuggingFaceEmbeddings(BaseEmbeddings):
    """使用开源的 SentenceTransformer 模型进行文本向量化"""

    @classmethod
    def allowed_params(cls):
        return {
            "model": "模型名称",
            **BaseEmbeddings.allowed_params()
        }

    def __init__(self, model: str=None, **kwargs):
        raise_invalid_params(kwargs, self.__class__.allowed_params())

        try:
            from sentence_transformers import SentenceTransformer
            import torch
        except ImportError:
            raise ImportError(
                "Could not import sentence-transformers and torch package. "
                "Please install it via 'pip install -U sentence-transformers torch'"
            )

        super().__init__(
            model=model or "all-MiniLM-L6-v2",
            **kwargs
        )
        self.client = SentenceTransformer(self.model, **kwargs)

        # 检查是否有可用的 CUDA GPU
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.client = self.client.to(self.device)

    def query(self, text: str) -> List[float]:
        """
        查询文本向量。
        """
        return self.embed_documents([text])[0]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        编码文本向量。
        """
        return self.client.encode(texts, convert_to_tensor=False, device=self.device).tolist()
