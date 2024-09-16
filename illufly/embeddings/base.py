from typing import List, Union
from ..agent import BaseAgent

class BaseEmbeddings(BaseAgent):
    """
    句子向量模型。
    """

    def __init__(self, model: str=None, api_key: str=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model = model
        self.api_key = api_key

    def call(self, prompt: Union[str, List[dict], "Template"], *args, **kwargs):
        raise NotImplementedError("暂时没有可用的方法")

    def query(self, text: str, *args, **kwargs) -> List[float]:
        """Embed query text."""

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed search docs."""
