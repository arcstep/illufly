from typing import List, Union
from ...utils import minify_text
from ...types import VectorDB, TextBlock, Document
from ...io import log, alog

import time
import numpy as np

class FaissDB(VectorDB):
    def __init__(self, *args, train: bool=None, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            import faiss
        except ImportError:
            raise RuntimeError(
                "Could not import faiss package. "
                "Please install it via 'pip install -U faiss-cpu faiss-gpu'"
            )

        self.train = train if train is not None else True
        self.index = faiss.IndexFlatL2(self.dim) 

        self.documents = self.embeddings.last_output[:]
        self.add(self.documents)
    
    def add(self, docs: Union[List[Document], List[str], str]):
        if isinstance(docs, str):
            docs = [Document(docs)]
        elif isinstance(docs, list):
            _docs = []
            for doc in docs:
                if isinstance(doc, str):
                    _docs.append(Document(doc))
                else:
                    _docs.append(doc)
            docs = _docs
        else:
            raise ValueError(f"docs 必须是字符串或 Document 类型列表，但实际为: {type(docs)}")

        vectors = self._process_embeddings(docs)
        if vectors is not None and len(vectors) > 0:
            if self.train:
                self.index.train(vectors)
            self.index.add(vectors)
            self.documents.extend(docs)

    def _process_embeddings(self, docs: List[Document]):
        """
        处理 embeddings.last_output 并返回 NumPy 数组。
        """
        embedded_docs = [d for d in docs if 'embeddings' in d.metadata]
        not_embedded_docs = [d for d in docs if 'embeddings' not in d.metadata]

        if not_embedded_docs:
            new_embeddings = self.embeddings(not_embedded_docs)
            embedded_docs.extend(new_embeddings)

        if embedded_docs:
            vectors = [d.metadata['embeddings'] for d in embedded_docs]
            return np.array(vectors, dtype='float32')  # 将列表转换为NumPy数组
        return None

    def query(self, text: str, top_k: int=None, **kwargs):
        """
        查询向量。
        """
        if len(self.documents) == 0:
            yield TextBlock("info", "FaissDB 中没有数据")
            return

        # 对输入字符串做向量编码并查询
        vectors = [self.embeddings.query(text)]
        vectors = np.array(vectors, dtype='float32')  # 将查询向量转换为NumPy数组
        distances, indices = self.index.search(vectors, top_k or self.top_k)

        # 筛选出文档
        valid_indices = indices[0][indices[0] >= 0]
        self._last_output = [(distances[0][i], self.documents[valid_indices[i]]) for i in range(len(valid_indices))]
        
        # 按距离排序
        self._last_output.sort(key=lambda x: x[0])
        
        for distance, doc in self._last_output:
            yield TextBlock("info", f"[{distance:.3f}] {doc.metadata['source']}: {minify_text(doc.text)}")
