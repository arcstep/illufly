from typing import List, Union
from ..base import Runnable
from ....core.document import Document
from ....utils import hash_text, clean_filename, raise_invalid_params
from ....config import get_env
from ....io import EventBlock

import os
import pickle

class BaseEmbeddings(Runnable):
    """
    句子嵌入模型。

    使用向量模型，将文本转换为向量，以便入库或查询。
    Document(text, meta={'source': str}) -> Document(text, meta={'embeddings': Vectors})

    例如：
    ```
    from illufly.types import Document
    from illufly.embeddings import TextEmbeddings # 通义千问文本向量模型

    embeddings = TextEmbeddings()
    docs = [Document("这是一个测试文本", meta={"source": "test"})]
    embeddings(docs)
    print(embeddings.last_output[0].meta['embeddings'])
    ```
    """
    @classmethod
    def allowed_params(cls):
        return {
            "model": "文本嵌入模型的名称",
            "base_url": "BASE_URL",
            "api_key": "API_KEY",
            "dim": "编码时使用的向量维度",
            "max_lines": "每次编码时处理的最大行数",
            **Runnable.allowed_params()
        }

    def __init__(self, model: str=None, base_url: str=None, api_key: str=None, dim: int=None, max_lines: int=None, **kwargs):
        raise_invalid_params(kwargs, self.__class__.allowed_params())

        super().__init__(**kwargs)
        self.dim = dim
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.max_lines = max_lines or 5
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
        **kwargs
    ) -> List[Document]:
        """
        将文本字符串或 Document 类型，转换为带有文本向量的 Document 列表。

        如果提供参数是字符串，则表示查询模式，自动填写 source 为 '__query__'。
        (这可能在使用某些模型时有必要，例如通义千问的 embedding-v2 以下版本)
        """
        self._last_output = []
        if isinstance(docs, str):
            docs = [Document(docs, meta={'source': '__query__'})]
        elif isinstance(docs, Document):
            docs.meta['source'] = '__query__'

        if not isinstance(docs, list):
            raise ValueError("docs 必须是字符串或 Document 类型列表，但实际为: {type(docs)}")

        vector_folder = self._get_embeddings_folder()

        for index, d in enumerate(docs):
            if isinstance(d, str):
                docs[index] = Document(d)
            elif not isinstance(d, Document):
                raise ValueError(f"文档类型错误: {type(d)}")

        yield from self._process_batch(docs, vector_folder)

        self._last_output = docs
        return docs

    def _process_batch(self, docs, vector_folder):
        batch_texts = []
        batch_docs = []

        for i in range(0, len(docs), self.max_lines):
            batch = docs[i:i + self.max_lines]
            batch_texts = [d.text for d in batch]
            batch_docs = batch

            # 检查哪些文件已经存在
            existing_files = self._check_existing_files(batch_docs, batch_texts, vector_folder)
            batch_texts = [text for text, exists in zip(batch_texts, existing_files) if not exists]
            batch_docs = [doc for doc, exists in zip(batch_docs, existing_files) if not exists]

            if batch_texts:
                yield EventBlock("info", f"文本向量转换 {sum(len(d.text) for d in batch_docs)} 字 / {len(batch_docs)} 个文件")
                vectors = self.embed_documents(batch_texts)
                yield from self._save_vectors_to_cache(batch_docs, batch_texts, vectors, vector_folder)

    def _check_existing_files(self, docs, batch_texts, vector_folder):
        existing_files = []
        for index, text in enumerate(batch_texts):
            vector_path = hash_text(text) + ".emb"
            source = clean_filename(docs[index].meta['source'])
            cache_path = os.path.join(vector_folder, source or "no_source", vector_path)
            if os.path.exists(cache_path):
                with open(cache_path, 'rb') as f:
                    docs[index].meta['embeddings'] = pickle.load(f)
                existing_files.append(True)
            else:
                existing_files.append(False)
        return existing_files

    def _save_vectors_to_cache(self, docs, batch_texts, vectors, vector_folder):
        for index, text in enumerate(batch_texts):
            vector_path = hash_text(text) + ".emb"
            source = clean_filename(docs[index].meta['source'])
            cache_path = os.path.join(vector_folder, source or "no_source", vector_path)
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, 'wb') as f:
                pickle.dump(vectors[index], f)
                docs[index].meta['embeddings'] = vectors[index]
                yield EventBlock('info', f'wrote embedding cache {cache_path} {text[0:50]}{"..." if len(text) > 50 else ""}')
