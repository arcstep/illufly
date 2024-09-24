from typing import List, Union
from ..base import Runnable
from ..embeddings import BaseEmbeddings

class VectorDB(Runnable):
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
            yield from self.embeddings.call(text)
        emb_str = self.embeddings.last_output
        yield from self.query(emb_str)
