from abc import ABC, abstractmethod
from typing import List, Union
from pydantic import BaseModel, Field

from ..utils import hash_text, clean_filename, raise_invalid_params
from ..rocksdb import IndexedRocksDB, default_rocksdb

from .models import EmbeddingText

import hashlib
import logging

class BaseEmbeddings(ABC):
    """句子嵌入模型"""

    def __init__(
        self,
        model: str=None,
        dim: int=None,
        output_type: str=None,
        max_lines: int=None,
        db: IndexedRocksDB=None,
        **kwargs
    ):
        self.dim = dim
        self.model = model
        self.output_type = output_type or "dense"
        self.max_lines = max_lines or 5
        self.db = db or default_rocksdb
        self.db.register_model(EmbeddingText.__name__, EmbeddingText)
        self._logger = logging.getLogger(self.__class__.__name__)

    async def _sync_embed_texts(self, texts: List[str]) -> List[List[float]]:
        """将文本转换为向量，以便入库"""
        pass

    async def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        """将文本转换为向量，以便入库"""
        pass

    def sync_embed_texts(
        self,
        texts: Union[str, List[str]],
        **kwargs
    ) -> List[EmbeddingText]:
        """
        将文本字符串或 EmbeddingText 类型，转换为带有文本向量的 EmbeddingText 列表。
        """
        texts = [texts] if isinstance(texts, str) else texts

        if not isinstance(texts, list):
            raise ValueError("texts 必须是字符串列表")

        embedding_texts = []

        for i in range(0, len(texts), self.max_lines):
            batch_texts = texts[i:i + self.max_lines]

            # 检查哪些文本已经嵌入
            to_embedding = []
            for text in batch_texts:
                found_embedding = self.db.get(EmbeddingText.get_key(self.model, self.dim, self.output_type, text))
                if found_embedding:
                    embedding_texts.append(found_embedding)
                else:
                    to_embedding.append(text)

            # 嵌入文本
            if to_embedding:
                vectors = self._sync_embed_texts(to_embedding)
                emb_texts = [
                    EmbeddingText(
                        text=text,
                        model=self.model,
                        dim=len(vector),
                        output_type=self.output_type,
                        vector=vector
                    )
                    for text, vector
                    in zip(to_embedding, vectors)
                ]
                embedding_texts.extend(emb_texts)
                self._logger.info(f"嵌入 `{to_embedding[0][:20]}` 等 {len(emb_texts)} 个文本")
                for emb_text in emb_texts:
                    key = EmbeddingText.get_key(self.model, self.dim, self.output_type, emb_text.text)
                    self.db.update_with_indexes(EmbeddingText.__name__, key, emb_text)

        # 确保向量维度一致
        expected_dim = self.dim
        for emb in embedding_texts:
            if len(emb.vector) != expected_dim:
                raise ValueError(
                    f"向量维度不符，期望{expected_dim}，实际{len(emb.vector)}"
                )
        
        return embedding_texts

    async def embed_texts(
        self,
        texts: Union[str, List[str]],
        **kwargs
    ) -> List[EmbeddingText]:
        """
        将文本字符串或 EmbeddingText 类型，转换为带有文本向量的 EmbeddingText 列表。
        """
        texts = [texts] if isinstance(texts, str) else texts

        if not isinstance(texts, list):
            raise ValueError("texts 必须是字符串列表")

        embedding_texts = []

        for i in range(0, len(texts), self.max_lines):
            batch_texts = texts[i:i + self.max_lines]

            # 检查哪些文本已经嵌入
            to_embedding = []
            for text in batch_texts:
                found_embedding = self.db.get(EmbeddingText.get_key(self.model, self.dim, self.output_type, text))
                if found_embedding:
                    embedding_texts.append(found_embedding)
                else:
                    to_embedding.append(text)

            # 嵌入文本
            if to_embedding:
                vectors = await self._embed_texts(to_embedding)
                emb_texts = [
                    EmbeddingText(
                        text=text,
                        model=self.model,
                        dim=len(vector),
                        output_type=self.output_type,
                        vector=vector
                    )
                    for text, vector
                    in zip(to_embedding, vectors)
                ]
                embedding_texts.extend(emb_texts)
                self._logger.info(f"嵌入 `{to_embedding[0][:20]}` 等 {len(emb_texts)} 个文本")
                for emb_text in emb_texts:
                    key = EmbeddingText.get_key(self.model, self.dim, self.output_type, emb_text.text)
                    self.db.update_with_indexes(EmbeddingText.__name__, key, emb_text)

        return embedding_texts