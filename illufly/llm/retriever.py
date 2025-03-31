from typing import List, Any, Dict, Union

import asyncio
import logging
import hashlib

from .base import LiteLLM

class ChromaRetriever():
    """
    基于 Chroma 向量数据库的检索器
    """

    def __init__(self, client=None, embedding_config: Dict[str, Any] = {}, chroma_config: Dict[str, Any] = {}):
        model = embedding_config.pop("model", "text-embedding-3-small")
        self.llm = LiteLLM(model=model, **embedding_config)
        self.client = client
        if client is None:
            try:
                import chromadb
                self.client = chromadb.Client(**chroma_config)
            except ImportError:
                raise ImportError(
                    "Could not import chromadb package. "
                    "Please install it via 'pip install -U chromadb'"
                )
        self._logger = logging.getLogger(__name__)

    def create_collection(self, name: str, chroma_config: Dict[str, Any] = {}) -> Any:
        """创建集合"""
        collection = self.client.create_collection(name, **chroma_config)
        self._logger.info(f"创建集合: {name}")
        return collection

    def delete_collection(self, name: str, chroma_config: Dict[str, Any] = {}) -> Any:
        """删除集合"""
        return self.client.delete_collection(name, **chroma_config)
    
    def get_ids(self, texts: List[str]) -> List[str]:
        """获取文本的ids"""
        return [hashlib.md5(text.encode('utf-8')).hexdigest() for text in texts]

    async def add(
        self,
        texts: List[str],
        collection_name: str = None,
        metadatas: List[Dict[str, Any]] = None,
        embedding_config: Dict[str, Any] = {},
        chroma_config: Dict[str, Any] = {},
    ) -> None:
        """添加文本，如果存在就更新"""
        collection_name = collection_name or "default"

        # 输入必须是字符串列表
        texts = [texts] if isinstance(texts, str) else texts

        # 元数据必须是字典列表
        if metadatas is not None:
            if isinstance(metadatas, dict):
                metadatas = [metadatas]
            if not isinstance(metadatas, list):
                raise ValueError("metadatas 必须是列表")
            if len(metadatas) != len(texts):
                raise ValueError("metadatas 的长度必须与 texts 的长度相同")

        # 确认集合存在
        collection = self.client.get_or_create_collection(collection_name)

        # 获取文本索引
        resp = await self.llm.aembedding(texts, **embedding_config)
        embeddings = [e.embedding for e in resp.data]
        ids = self.get_ids(texts)
        return collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas, **chroma_config)

    def delete(
        self,
        texts: List[str] = None,
        ids: List[str] = None,
        collection_name: str = None,
        where: Dict[str, Any] = None,
        chroma_config: Dict[str, Any] = {},
    ) -> None:
        """删除文本"""
        collection_name = collection_name or "default"
        collection = self.client.get_or_create_collection(collection_name)
        if texts is not None:
            ids = self.get_ids(texts)
        return collection.delete(ids=ids, where=where, **chroma_config)

    async def query(
        self,
        texts: Union[str, List[str]],
        collection_name: str = None,
        embedding_config: Dict[str, Any] = {},
        chroma_config: Dict[str, Any] = {},
    ) -> List[str]:
        """查询"""
        collection_name = collection_name or "default"
        collection = self.client.get_or_create_collection(collection_name)

        # 输入必须是字符串列表
        texts = [texts] if isinstance(texts, str) else texts

        resp = await self.llm.aembedding(texts, **embedding_config)
        # print(resp)
        query_embeddings = [e.embedding for e in resp.data]
        return collection.query(query_embeddings=query_embeddings, **chroma_config)
