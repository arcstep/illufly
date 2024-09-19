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

    如果当作BaseAgent来使用，其行为是：
    - 将给定字符串列表转换为向量，并返回一个新的 Document 列表
    - 如果已经存在缓存，则直接读取，而不需要再做向量编码
    - 如果指定了 batch_mode 为 True，则先批量生成缓存，再读取
    """

    def __init__(self, model: str=None, api_key: str=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model = model
        self.api_key = api_key
        self._output = []

    @property
    def output(self):
        return self._output

    def query(self, text: str, *args, **kwargs) -> List[float]:
        """Embed query text."""

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed search docs."""

    def get_embeddings_folder(self):
        return os.path.join(get_env("ILLUFLY_CACHE_EMBEDDINGS"), self.__class__.__name__, self.model)

    def call(self, docs: Union[List[str], List[Document]], batch_mode: bool=False, batch_size=None, **kwargs):
        """
        将向量文本嵌入到数据库。
        """
        if not isinstance(docs, list):
            raise ValueError("docs 必须是字符串或 Document 类型列表，但实际为: {type(docs)}")

        vector_folder = self.get_embeddings_folder()

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
                    print("batch ", batch_texts)
                    vectors = self.embed_documents(batch_texts)
                    for block in self._save_vectors_to_cache(docs, batch_texts, vectors, vector_folder):
                        yield block
                    batch_texts = []
                    texts_size = 0
                batch_texts.append(d.text)
                texts_size += text_length
            if batch_texts:
                print("batch2 ", batch_texts)
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
                vectors = self.embed_documents([d.text])
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, 'wb') as f:
                    d.metadata['embeddings'] = vectors[0]
                    pickle.dump(vectors[0], f)
                    yield TextBlock('info', f'wrote embedding cache {cache_path} {d.text[0:50]}{"..." if len(d.text) > 50 else ""}')

        self._output = docs

    def _save_vectors_to_cache(self, docs, batch_texts, vectors, vector_folder):
        for index, text in enumerate(batch_texts):
            vector_path = hash_text(text) + ".emb"
            source = clean_filename(docs[index].metadata['source'])
            cache_path = os.path.join(vector_folder, source or "no_source", vector_path)
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, 'wb') as f:
                pickle.dump(vectors[index], f)
                yield TextBlock('info', f'wrote embedding cache {cache_path} {text[0:50]}{"..." if len(text) > 50 else ""}')
