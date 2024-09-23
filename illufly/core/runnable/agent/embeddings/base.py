from typing import List, Union
from ..base import BaseAgent
from .....core.document import Document
from .....utils import get_env, hash_text, clean_filename
from .....config import get_env
from .....io import TextBlock

import os
import pickle

class BaseEmbeddings(BaseAgent):
    """
    句子嵌入模型。
    """

    def __init__(self, model: str=None, api_key: str=None, dim: int=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dim = dim if dim else 1024
        self.model = model
        self.api_key = api_key
        self.clear()
    
    def clear(self):
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
        batch_mode: bool=False,
        batch_size=None,
        **kwargs
    ) -> List[Document]:
        """
        将文本字符串转换为文本向量。

        由于有些向量模型对查询和存储的编码方式不同，因此要求其分别实现 query 方法和 embed_documents 方法。

        因此，这里也有一些重要约定：
        - 如果 docs 是 Document 类型，且 metadata.source 的值为 __query__，则按照查询模式编码
        - 如果 docs 是作为一个字符串提供，就在转换时自动补充一个 __query__ 的值（在使用中应当尽量按这样的方式使用查询模式）
        - 如果 docs 的 metadata.source 是其他值，则按照存储编码来做转换
        - 无论哪种类型，如果缓存中已经转换过就不再重新转换（除非清理缓存）
        - 如果指定了 batch_mode 为 True，则分批次转换

        返回值是包含了向量转换的 Document 列表。
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

        # 批量构建嵌入缓存
        max_batch_size = batch_size or get_env("ILLUFLY_EMBEDDINGS_BATCH_SIZE")
        if batch_mode:
            batch_texts = []
            texts_size = 0
            for d in docs:
                text_length = len(d.text)
                if batch_texts and texts_size + text_length > max_batch_size:
                    yield TextBlock("info", f"文本向量转换 {texts_size} 字 / {len(batch_texts)} 个文件")
                    vectors = self.embed_documents(batch_texts)
                    for block in self._save_vectors_to_cache(docs, batch_texts, vectors, vector_folder):
                        yield block
                    batch_texts = []
                    texts_size = 0
                batch_texts.append(d.text)
                texts_size += text_length
            if batch_texts:
                yield TextBlock("info", f"文本向量转换 {texts_size} 字 / {len(batch_texts)} 个文件")
                vectors = self.embed_documents(batch_texts)
                for block in self._save_vectors_to_cache(docs, batch_texts, vectors, vector_folder):
                    yield block

        warn_times = 0
        for d in docs:
            vector_path = hash_text(d.text) + ".emb"
            source = clean_filename(d.metadata['source'])
            cache_path = os.path.join(vector_folder, source or "no_source", vector_path)
            if os.path.exists(cache_path):
                if os.path.getsize(cache_path) == 0:
                    continue
                with open(cache_path, 'rb') as f:
                    embeddings = pickle.load(f)
                    if not embeddings:
                        d.metadata['embeddings'] = None
                        warn_times += 1
                        yield TextBlock('warn', f'无法读取缓存文件：{cache_path}')
                        if warn_times >= 5:
                            raise RuntimeError("太多缓存文件无法读取！")
                        continue
                    d.metadata['embeddings'] = embeddings
            else:
                if d.metadata['source'] == '__query__':
                    vectors = self.query(d.text)
                else:
                    vectors = self.embed_documents([d.text])
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, 'wb') as f:
                    d.metadata['embeddings'] = vectors[0]
                    pickle.dump(vectors[0], f)
                    yield TextBlock('info', f'wrote embedding cache {cache_path} {d.text[0:50]}{"..." if len(d.text) > 50 else ""}')

        self._last_output = docs

    def _save_vectors_to_cache(self, docs, batch_texts, vectors, vector_folder):
        for index, text in enumerate(batch_texts):
            vector_path = hash_text(text) + ".emb"
            source = clean_filename(docs[index].metadata['source'])
            cache_path = os.path.join(vector_folder, source or "no_source", vector_path)
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, 'wb') as f:
                pickle.dump(vectors[index], f)
                yield TextBlock('info', f'wrote embedding cache {cache_path} {text[0:50]}{"..." if len(text) > 50 else ""}')
