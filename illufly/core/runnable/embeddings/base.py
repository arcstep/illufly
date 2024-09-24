from typing import List, Union
from ..base import Runnable
from ....core.document import Document
from ....utils import hash_text, clean_filename
from ....config import get_env
from ....io import TextBlock

import os
import pickle

class BaseEmbeddings(Runnable):
    """
    句子嵌入模型。

    使用向量模型，将文本转换为向量，以便入库或查询。
    Document(text, metadata={'source': str}) -> Document(text, metadata={'embeddings': Vectors})

    例如：
    ```
    from illufly import Document
    from illufly.types import BaseEmbeddings

    embeddings = BaseEmbeddings(model="text-embedding-3-large")
    doc = Document("这是一个测试文本")
    embeddings(doc)
    print(embeddings.last_output[0].metadata['embeddings'])
    ```
    """

    def __init__(self, model: str=None, api_key: str=None, dim: int=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dim = dim if dim else 1024
        self.model = model
        self.api_key = api_key
        self.clear_output()

    def clear_output(self):
        self._last_output = []

    def query(self, text: str, *args, **kwargs) -> List[float]:
        """将文本转换为向量，以便查询"""

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """将文本转换为向量，以便入库"""

    def _get_embeddings_folder(self):
        return os.path.join(get_env("ILLUFLY_CACHE_EMBEDDINGS"), self.__class__.__name__, self.model)

    def call(
        self,
        docs: Union[str, List[str], List[Document]],
        batch_size: int=None,
        **kwargs
    ) -> List[Document]:
        """
        将文本字符串或 Document 类型，转换为带有文本向量的 Document 列表。

        如果提供参数是字符串，则表示查询模式，自动填写 source 为 '__query__'。
        (这可能在使用某些模型时有必要，例如通义千问的 embedding-v2 以下版本)
        """
        if isinstance(docs, str):
            docs = [Document(docs, metadata={'source': '__query__'})]
        elif isinstance(docs, Document):
            docs.metadata['source'] = '__query__'

        if not isinstance(docs, list):
            raise ValueError("docs 必须是字符串或 Document 类型列表，但实际为: {type(docs)}")

        vector_folder = self._get_embeddings_folder()

        for index, d in enumerate(docs):
            if isinstance(d, str):
                docs[index] = Document(d)
            elif not isinstance(d, Document):
                raise ValueError(f"文档类型错误: {type(d)}")

        yield from self._process_batch(docs, batch_size, vector_folder)

        self._last_output = docs
        return docs

    def _process_batch(self, docs, batch_size, vector_folder):
        max_batch_size = batch_size or get_env("ILLUFLY_EMBEDDINGS_BATCH_SIZE")
        batch_texts = []
        batch_docs = []
        texts_size = 0

        for d in docs:
            vector_path = hash_text(d.text) + ".emb"
            source = clean_filename(d.metadata['source'])
            cache_path = os.path.join(vector_folder, source or "no_source", vector_path)

            if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
                with open(cache_path, 'rb') as f:
                    embeddings = pickle.load(f)
                    if embeddings:
                        d.metadata['embeddings'] = embeddings
                        continue

            text_length = len(d.text)
            if batch_texts and texts_size + text_length > max_batch_size:
                yield TextBlock("info", f"文本向量转换 {texts_size} 字 / {len(batch_texts)} 个文件")
                vectors = self.embed_documents(batch_texts)
                yield from self._save_vectors_to_cache(batch_docs, batch_texts, vectors, vector_folder)
                batch_texts = []
                batch_docs = []
                texts_size = 0

            batch_texts.append(d.text)
            batch_docs.append(d)
            texts_size += text_length

        if batch_texts:
            yield TextBlock("info", f"文本向量转换 {texts_size} 字 / {len(batch_texts)} 个文件")
            vectors = self.embed_documents(batch_texts)
            yield from self._save_vectors_to_cache(batch_docs, batch_texts, vectors, vector_folder)

    def _save_vectors_to_cache(self, docs, batch_texts, vectors, vector_folder):
        for index, text in enumerate(batch_texts):
            vector_path = hash_text(text) + ".emb"
            source = clean_filename(docs[index].metadata['source'])
            cache_path = os.path.join(vector_folder, source or "no_source", vector_path)
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, 'wb') as f:
                pickle.dump(vectors[index], f)
                docs[index].metadata['embeddings'] = vectors[index]
                yield TextBlock('info', f'wrote embedding cache {cache_path} {text[0:50]}{"..." if len(text) > 50 else ""}')
