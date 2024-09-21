from typing import List, Union
from ..base import BaseAgent
from ..embeddings import BaseEmbeddings

class VectorDB(BaseAgent):
    """
    向量数据库。
    """

    def __init__(self, embeddings: BaseEmbeddings, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.embeddings = embeddings
        self.dim = self.embeddings.dim

    def query(self, vector: str, *args, **kwargs):
        pass

    def add(self, vector: str, *args, **kwargs):
        pass

    def call(self, text: str, *args, **kwargs):
        if text:
            for block in self.embeddings.call(text):
                yield block
        emb_str = self.embeddings.last_output
        for block in self.query(emb_str):
            yield block
