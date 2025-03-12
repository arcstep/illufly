from ..base_vector_db import BaseVectorDB, TextIndexing
from ..base_embeddings import BaseEmbeddings
from ..models import EmbeddingText
from typing import List, Any, Dict, Union

import asyncio

class ChromaDB(BaseVectorDB):
    def __init__(self, embeddings: BaseEmbeddings, client=None, **kwargs):
        super().__init__(embeddings, **kwargs)
        self.client = client
        if client is None:
            try:
                import chromadb
                self.client = chromadb.Client()
            except ImportError:
                raise ImportError(
                    "Could not import chromadb package. "
                    "Please install it via 'pip install -U chromadb'"
                )

    def create_collection(self, name: str, **kwargs) -> Any:
        """创建集合"""
        collection = self.client.create_collection(name, **kwargs)
        self._logger.info(f"创建集合: {name}")
        return collection

    def delete_collection(self, name: str, **kwargs) -> Any:
        """删除集合"""
        return self.client.delete_collection(name)

    async def add(self, texts: List[str], collection_name: str = None, metadatas: List[Dict[str, Any]] = None, **kwargs) -> None:
        """添加文本，如果存在就更新"""
        collection_name = collection_name or "default"

        if not isinstance(texts, list):
            raise ValueError("texts 必须是列表")
        if any(not isinstance(text, str) for text in texts):
            raise ValueError("texts 必须是字符串列表")

        # 确认集合存在
        collection = self.client.get_or_create_collection(collection_name)

        # 获取文本索引
        embs = await self.embeddings.embed_texts(texts)

        # 提取文本、向量、索引键和元数据
        texts = [e.text for e in embs]
        if metadatas is not None:
            meta = [{**e.model_dump(exclude={"vector"}), **metadata} for e, metadata in zip(embs, metadatas)]
        else:
            meta = [e.model_dump(exclude={"vector"}) for e in embs]
        ids = [EmbeddingText.get_key(e.model, e.dim, e.output_type, e.text) for e in embs]
        embeddings = [e.vector for e in embs]
        return collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=meta)

    def delete(
        self,
        texts: List[str],
        collection_name: str,
        where: Dict[str, Any] = None,
        **kwargs
    ) -> None:
        """删除文本"""
        collection_name = collection_name or "default"
        collection = self.client.get_or_create_collection(collection_name)
        e = self.embeddings
        keys = [EmbeddingText.get_key(e.model, e.dim, e.output_type, text) for text in texts]
        return collection.delete(ids=keys, where=where)

    async def query(
        self,
        texts: Union[str, List[str]],
        collection_name: str = None,
        n_results: int = None,
        where: Dict[str, Any] = None,
        where_document: Dict[str, Any] = None,
        **kwargs
    ) -> List[str]:
        """查询"""
        collection_name = collection_name or "default"
        collection = self.client.get_or_create_collection(collection_name)

        if n_results is not None:
            kwargs["n_results"] = n_results
        if where:
            kwargs["where"] = where
        if where_document:
            kwargs["where_document"] = where_document

        embeddings = await self.embeddings.embed_texts(texts)
        query_embeddings = [e.vector for e in embeddings]
        results = collection.query(query_embeddings=query_embeddings, **kwargs)
        return results

class RemoteChromaDB(BaseVectorDB):
    def __init__(self, embeddings: BaseEmbeddings, host: str = None, port: int = None, **kwargs):
        super().__init__(embeddings, **kwargs)
        
        # 保存参数但不初始化客户端
        self._host = host
        self._port = port

        self._client_initialized = False
        self.client = None
        
    async def _ensure_client(self):
        """确保客户端已初始化"""
        if not self._client_initialized:
            try:
                import chromadb
                # 按照官方示例，AsyncHttpClient需要await
                self.client = await chromadb.AsyncHttpClient(host=self._host, port=self._port)
                self._client_initialized = True
            except ImportError:
                raise ImportError(
                    "Could not import chromadb package. "
                    "Please install it via 'pip install -U chromadb'"
                )

    async def create_collection(self, name: str, **kwargs):
        """创建集合"""
        await self._ensure_client()
        return await self.client.create_collection(name, **kwargs)

    async def delete_collection(self, name: str) -> Any:
        """删除集合"""
        await self._ensure_client()
        return await self.client.delete_collection(name)

    async def add(self, texts: List[str], collection_name: str = None, metadatas: List[Dict[str, Any]] = None, **kwargs) -> Any:
        """添加文本，如果存在就更新"""
        await self._ensure_client()

        collection_name = collection_name or "default"
        if isinstance(texts, str):
            texts = [texts]

        if not isinstance(texts, list):
            raise ValueError("texts 必须是列表")
        if any(not isinstance(text, str) for text in texts):
            raise ValueError("texts 必须是字符串列表")
        if metadatas is not None and not isinstance(metadatas, list):
            raise ValueError("metadatas 必须是列表")
        if metadatas is not None and len(metadatas) != len(texts):
            raise ValueError("metadatas 的长度必须与 texts 的长度相同")

        # 确认集合存在
        collection = await self.client.get_or_create_collection(collection_name)

        # 获取文本索引
        embs = await self.embeddings.embed_texts(texts)

        # 提取文本、向量、索引键和元数据
        texts = [e.text for e in embs]
        if metadatas is not None:
            metadatas = [{**e.model_dump(exclude={"vector"}), **metadata} for e, metadata in zip(embs, metadatas)]
        else:
            metadatas = [e.model_dump(exclude={"vector"}) for e in embs]
        ids = [EmbeddingText.get_key(e.model, e.dim, e.output_type, e.text) for e in embs]
        embeddings = [e.vector for e in embs]

        return await collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)

    async def delete(
        self,
        collection_name: str,
        texts: List[str],
        where: Dict[str, Any] = None,
        **kwargs
    ) -> None:
        """删除文本"""
        await self._ensure_client()

        collection_name = collection_name or "default"
        collection = await self.client.get_or_create_collection(collection_name)
        e = self.embeddings
        keys = [EmbeddingText.get_key(e.model, e.dim, e.output_type, text) for text in texts]
        return await collection.delete(ids=keys, where=where)

    async def query(
        self,
        texts: Union[str, List[str]],
        collection_name: str = None,
        n_results: int = None,
        where: Dict[str, Any] = None,
        where_document: Dict[str, Any] = None,
        **kwargs
    ) -> List[str]:
        """查询"""
        await self._ensure_client()

        collection_name = collection_name or "default"
        collection = await self.client.get_or_create_collection(collection_name)

        if n_results is not None:
            kwargs["n_results"] = n_results
        if where:
            kwargs["where"] = where
        if where_document:
            kwargs["where_document"] = where_document

        embeddings = await self.embeddings.embed_texts(texts)
        query_embeddings = [e.vector for e in embeddings]
        results = await collection.query(query_embeddings=query_embeddings, **kwargs)
        return results
