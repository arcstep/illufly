from ..agent import BaseAgent

class BaseEmbeddings(BaseAgent):
    """
    向量模型。
    """

    def call(self, text: str) -> List[float]:
        """Embed query text."""

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed search docs."""
