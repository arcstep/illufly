from typing import List, Union, Callable, Generator, AsyncGenerator
from ...utils import minify_text
from ...types import VectorDB, EventBlock, Document
from ...io import log, alog
from ...core.runnable import MarkMeta
from ...utils import raise_invalid_params

import time
import numpy as np

class FaissDB(VectorDB):
    @classmethod
    def allowed_params(cls):
        return {
            "train": "是否在加载数据时训练模型",
            **VectorDB.allowed_params()
        }

    def __init__(self, train: bool=None, **kwargs):
        raise_invalid_params(kwargs, self.__class__.allowed_params())

        super().__init__(**kwargs)
        try:
            import faiss
        except ImportError:
            raise ImportError(
                "Could not import faiss package. "
                "Please install it via 'pip install -U faiss-cpu faiss-gpu'"
            )

        self.train = train if train is not None else True
        self.index = faiss.IndexFlatL2(self.dim) 

        self.documents = self.embeddings.last_output[:]
        self.load_documents(self.documents)
    
    def load_text(self, text: str, source: str=None, **kwargs):
        mm = MarkMeta(**kwargs)
        docs = mm.load_text(text, source)

        self.load_documents(docs)

    def load_documents(self, docs: List[Document], **kwargs):
        vectors = self._process_embeddings(docs)
        if vectors is not None and len(vectors) > 0:
            if self.train:
                self.index.train(vectors)
            self.index.add(vectors)
            self.documents.extend(docs)

    def load(
        self,
        dir: str=None,
        verbose: bool = False,
        handlers: List[Union[Callable, Generator, AsyncGenerator]] = None,
        call_func: Callable = None,
        **kwargs
    ):
        """
        使用 MarkMeta 的 load 方法从指定目录加载文件。
        """
        # 记录文档来源
        self.sources.append(dir)

        mm = MarkMeta(dir=dir, **kwargs)
        mm(verbose=verbose, handlers=handlers, action="load", **kwargs)

        vectors = self._process_embeddings(mm.last_output)
        if vectors is not None and len(vectors) > 0:
            if self.train:
                self.index.train(vectors)
            self.index.add(vectors)
            self.documents.extend(mm.last_output)

    def _process_embeddings(self, docs: List[Document]):
        """
        处理 embeddings.last_output 并返回 NumPy 数组。
        """
        embedded_docs = [d for d in docs if 'embeddings' in d.meta]
        not_embedded_docs = [d for d in docs if 'embeddings' not in d.meta]

        if not_embedded_docs:
            new_embeddings = self.embeddings(not_embedded_docs, verbose=self.verbose)
            embedded_docs.extend(new_embeddings)

        if embedded_docs:
            vectors = [d.meta['embeddings'] for d in embedded_docs]
            return np.array(vectors, dtype='float32')  # 将列表转换为NumPy数组
        return None

    def query(self, text: str, top_k: int=None, **kwargs) -> List[Document]:
        """
        查询向量。

        由于查询过程需要快速返回，因此不按迭代器返回。
        """
        if len(self.documents) == 0:
            return []
        elif not text or len(text.strip()) == 0:
            return []
        else:
            # 对输入字符串做向量编码并查询
            vectors = [self.embeddings.query(text)]
            vectors = np.array(vectors, dtype='float32')  # 将查询向量转换为NumPy数组
            distances, indices = self.index.search(vectors, top_k or self.top_k or 5)

            # 筛选出文档
            valid_indices = indices[0][indices[0] >= 0]
            results = [(distances[0][i], self.documents[valid_indices[i]]) for i in range(len(valid_indices))]

            # 按距离排序
            results.sort(key=lambda x: x[0])
            for distance, doc in results:
                doc.meta["distance"] = distance

            # 返回的结果是 Document 列表
            return [doc for _, doc in results]
