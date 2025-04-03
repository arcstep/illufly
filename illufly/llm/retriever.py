from typing import List, Any, Dict, Union

import asyncio
import logging
import hashlib

from .base import LiteLLM

import logging
logger = logging.getLogger(__name__)

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
    
    def _default_collection_metadata(self) -> Dict[str, Any]:
        return {
            "hnsw:space": "cosine",
            "hnsw:search_ef": 100
        }

    def get_or_create_collection(self, name: str, metadata: Dict[str, Any] = {}) -> Any:
        """创建集合"""
        metadata = {**self._default_collection_metadata(), **metadata}
        collection = self.client.get_or_create_collection(name, metadata=metadata)
        self._logger.info(f"创建集合: {name}")
        return collection

    def delete_collection(self, name: str, chroma_config: Dict[str, Any] = {}) -> Any:
        """删除集合"""
        return self.client.delete_collection(name, **chroma_config)
    
    def get_ids(self, texts: List[str]) -> List[str]:
        """获取文本的ids"""
        return [hashlib.md5(text.encode('utf-8')).hexdigest() for text in texts]

    def _deduplicate_texts(self, texts: Union[str, List[str]]) -> List[str]:
        """对输入文本进行去重处理
        
        Args:
            texts: 输入文本，可以是单个字符串或字符串列表
            
        Returns:
            List[str]: 去重后的文本列表
        """
        # 先确保是列表
        texts = [texts] if isinstance(texts, str) else texts
        # 使用字典保持顺序去重
        return list(dict.fromkeys(texts))

    async def add(
        self,
        texts: Union[str, List[str]],
        collection_name: str = None,
        user_id: str = None,
        metadatas: Union[str, List[Dict[str, Any]]] = None,
        embedding_config: Dict[str, Any] = {},
        collection_config: Dict[str, Any] = {},
        ids: List[str] = None
    ) -> None:
        """
        添加文本，如果存在就更新。

        Args:
            collection_name: 用来区分不同的内容集合，默认为 default
            texts: 检索的文本内容, 如果是QA记忆则应分别将问和答作为 texts 编码保存到向量数据库中
            user_id: 用来区分不同的用户, 放入metadata中, 查询时通过元数据过滤
            metadatas: 除了用户ID, 元数据中还可以包含记忆的主题、问题和答案
            embedding_config: 嵌入向量配置
            collection_config: 集合配置
            ids: 文档的唯一标识符，如果不提供则使用文本的哈希值
        """
        collection_name = collection_name or "default"
        collection_config = {**self._default_collection_metadata(), **collection_config}

        # 对输入文本去重
        texts = self._deduplicate_texts(texts)

        user_id = user_id or "default"

        # 元数据
        if metadatas is not None:
            if isinstance(metadatas, dict):
                metadatas = [metadatas]
            if not isinstance(metadatas, list):
                raise ValueError("metadatas 必须是列表")
            if len(metadatas) != len(texts):
                raise ValueError("metadatas 的长度必须与 texts 的长度相同")
        else:
            metadatas = [{} for _ in texts]
        
        metadatas = [{"user_id": user_id, **m} for m in metadatas]

        # 确认集合存在
        collection = self.client.get_or_create_collection(collection_name, metadata=collection_config)

        # 获取文本索引
        resp = await self.llm.aembedding(texts, **embedding_config)
        embeddings = [e['embedding'] for e in resp.data]
        
        # 如果没有提供ids，则使用文本哈希值作为ids
        if ids is None:
            ids = self.get_ids(texts)
        elif len(ids) != len(texts):
            raise ValueError("ids 的长度必须与 texts 的长度相同")

        logger.info(f"\nchroma add >>> {ids}, {texts}, {metadatas}")
        return collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)

    def delete(
        self,
        texts: List[str] = None,
        ids: List[str] = None,
        collection_name: str = None,
        where: Dict[str, Any] = None,
    ) -> None:
        """删除文本"""
        texts = self._deduplicate_texts(texts)
        collection_name = collection_name or "default"
        collection = self.client.get_collection(collection_name)
        if texts is not None:
            ids = self.get_ids(texts)
        return collection.delete(ids=ids, where=where)

    async def query(
        self,
        texts: Union[str, List[str]],
        threshold: float = 0.5,
        collection_name: str = None,
        user_id: str = None,
        embedding_config: Dict[str, Any] = {},
        query_config: Dict[str, Any] = {},
    ) -> List[Dict[str, List]]:
        """查询并按阈值过滤结果
        
        Args:
            texts: 查询文本，可以是单个字符串或字符串列表
            threshold: 相似度阈值，距离小于此值的结果会被保留
            collection_name: 集合名称
            user_id: 按用户ID过滤
            embedding_config: 嵌入向量配置
            query_config: ChromaDB查询配置，例如 {"n_results": 3} 表示返回3个结果
            
        Returns:
            List[Dict[str, List]]: 每个查询的过滤后结果，包含ids、documents和distances
        """
        collection_name = collection_name or "default"
        collection = self.client.get_or_create_collection(collection_name)

        # 对查询文本去重
        texts = self._deduplicate_texts(texts)

        # 确保查询配置包含必要的返回字段
        query_config.update({"include": ["documents", "distances", "metadatas"]})

        # 如果指定了用户ID, 则通过元数据过滤
        if user_id:
            if query_config.get("where", None) is None:
                query_config["where"] = {"user_id": user_id}
            else:
                query_config["where"]["user_id"] = user_id

        # 获取嵌入向量并查询
        resp = await self.llm.aembedding(texts, **embedding_config)
        query_embeddings = [e['embedding'] for e in resp.data]
        results = collection.query(query_embeddings=query_embeddings, **query_config)

        # 处理每个查询的结果
        final_results = []
        for i in range(len(texts)):
            # 使用阈值过滤结果
            filtered_indices = [
                j for j, distance in enumerate(results['distances'][i])
                if distance < threshold
            ]
            
            # 构建过滤后的结果
            filtered_result = {
                "text": texts[i],
                "ids": [results['ids'][i][j] for j in filtered_indices],
                "metadatas": [results['metadatas'][i][j] for j in filtered_indices],
                "documents": [results['documents'][i][j] for j in filtered_indices],
                "distances": [results['distances'][i][j] for j in filtered_indices]
            }
            final_results.append(filtered_result)

        return final_results
