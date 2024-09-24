from typing import List
from ...utils import minify_text
from ...types import VectorDB, TextBlock
from ...io import log, alog

import time
import numpy as np

class FaissDB(VectorDB):
    def __init__(self, *args, train: bool=True, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            import faiss
        except ImportError:
            raise RuntimeError(
                "Could not import faiss package. "
                "Please install it via 'pip install -U faiss-cpu faiss-gpu'"
            )

        docs = [d.metadata['embeddings'] for d in self.embeddings.last_output]
        if len(docs) == 0:
            raise ValueError("No embeddings found")
        docs = np.array(docs, dtype='float32')  # 将列表转换为NumPy数组
        self.index = faiss.IndexFlatL2(self.dim) 
        if train:
            self.index.train(docs)
        print("docs", docs)
        self.index.add(docs)

    def query(self, text: str, top_k: int=None, **kwargs):
        """
        查询向量。
        """
        vectors = [self.embeddings.query(text)]
        vectors = np.array(vectors, dtype='float32')  # 将查询向量转换为NumPy数组
        distances, indices = self.index.search(vectors, top_k or self.top_k)

        # 按距离排序
        sorted_indices = np.argsort(distances[0])
        sorted_distances = distances[0][sorted_indices]
        sorted_indices = indices[0][sorted_indices]

        # 筛选出文档
        valid_indices = sorted_indices[sorted_indices > 0]
        self._last_output = [self.embeddings.last_output[i] for i in valid_indices]
        for doc in self._last_output:
            yield TextBlock("info", f"{doc.metadata['source']}: {minify_text(doc.text)}")
