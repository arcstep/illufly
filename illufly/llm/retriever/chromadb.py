from typing import List, Any, Dict, Union

import asyncio
import logging
import hashlib

from .base import BaseRetriever
from ..litellm import LiteLLM

logger = logging.getLogger(__name__)

class ChromaRetriever(BaseRetriever):
    """
    基于 Chroma 向量数据库的检索器
    """

    def __init__(self, client=None, embedding_config: Dict[str, Any] = {}, chroma_config: Dict[str, Any] = {}):
        self.model = LiteLLM(model_type="embedding", **embedding_config)
        self.client = client
        if client is None:
            try:
                import chromadb
                from chromadb.config import Settings
                self.client = chromadb.Client(Settings(anonymized_telemetry=False), **chroma_config)
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
        metadatas: Union[Dict[str, Any], List[Dict[str, Any]]] = None,
        embedding_config: Dict[str, Any] = {},
        collection_config: Dict[str, Any] = {},
        ids: List[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        添加文本到向量库，如果存在就更新。

        Args:
            collection_name: 用来区分不同的内容集合，默认为 default
            texts: 检索的文本内容, 如果是QA记忆则应分别将问和答作为 texts 编码保存到向量数据库中
            user_id: 用来区分不同的用户, 放入metadata中, 查询时通过元数据过滤
            metadatas: 除了用户ID, 元数据中还可以包含记忆的主题、问题和答案
            embedding_config: 嵌入向量配置
            collection_config: 集合配置
            ids: 文档的唯一标识符，如果不提供则使用文本的哈希值
            
        Returns:
            添加结果统计
        """
        collection_name = collection_name or "default"
        collection_config = {**self._default_collection_metadata(), **collection_config}

        # 对输入文本去重
        texts = self._deduplicate_texts(texts)

        user_id = user_id or "default"

        # 标准化元数据
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
        resp = await self.model.aembedding(texts, **embedding_config)
        embeddings = [e['embedding'] for e in resp.data]
        
        # 如果没有提供ids，则使用文本哈希值作为ids
        if ids is None:
            ids = self.get_ids(texts)
        elif len(ids) != len(texts):
            raise ValueError("ids 的长度必须与 texts 的长度相同")

        logger.info(f"\nchroma add >>> {ids}, {texts}, {metadatas}")
        
        # 进行upsert操作
        collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
        
        return {
            "success": True,
            "added": len(texts),
            "skipped": 0,
            "original_count": len(texts)
        }

    async def delete(
        self,
        collection_name: str = None,
        user_id: str = None,
        texts: List[str] = None,
        ids: List[str] = None,
        where: Dict[str, Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """删除文本
        
        Args:
            collection_name: 集合名称
            user_id: 按用户ID删除
            texts: 要删除的文本列表
            ids: 要删除的文档ID列表
            where: 元数据过滤条件
        
        Returns:
            删除结果统计
        """
        try:
            collection_name = collection_name or "default"
            
            # 构建where条件
            if where is None:
                where = {}
            
            if user_id:
                where["user_id"] = user_id
            
            if texts is not None:
                texts = self._deduplicate_texts(texts)
                ids = self.get_ids(texts)
            
            # 确保集合存在
            try:
                collection = self.client.get_collection(collection_name)
            except Exception as e:
                return {"success": True, "deleted": 0, "message": f"集合不存在: {str(e)}"}
            
            # 执行删除
            collection.delete(ids=ids, where=where if where else None)
            
            return {"success": True, "deleted": 1, "message": "删除成功"}
        except Exception as e:
            logger.error(f"删除失败: {str(e)}")
            return {"success": False, "deleted": 0, "error": str(e)}

    async def query(
        self,
        query_texts: Union[str, List[str]],
        threshold: float = 0.5,
        collection_name: str = None,
        user_id: str = None,
        embedding_config: Dict[str, Any] = {},
        query_config: Dict[str, Any] = {},
        **kwargs
    ) -> List[Dict[str, Any]]:
        """查询并按阈值过滤结果
        
        Args:
            query_texts: 查询文本，可以是单个字符串或字符串列表
            threshold: 相似度阈值，距离小于此值的结果会被保留
            collection_name: 集合名称
            user_id: 按用户ID过滤
            embedding_config: 嵌入向量配置
            query_config: ChromaDB查询配置，例如 {"n_results": 3} 表示返回3个结果
            
        Returns:
            List[Dict[str, Any]]: 包含查询结果的列表
        """
        collection_name = collection_name or "default"
        
        try:
            collection = self.client.get_or_create_collection(collection_name)
        except Exception as e:
            logger.error(f"获取集合失败: {str(e)}")
            # 返回格式化的空结果
            if isinstance(query_texts, str):
                query_texts = [query_texts]
            return [{"query": text, "results": []} for text in query_texts]

        logger.info(f"\nchroma query >>> 开始查询")
        logger.info(f"集合名称: {collection_name}")
        logger.info(f"查询文本: {query_texts}")
        logger.info(f"阈值: {threshold}")
        logger.info(f"用户ID: {user_id}")
        logger.info(f"查询配置: {query_config}")

        # 对查询文本去重
        texts = self._deduplicate_texts(query_texts)
        logger.info(f"去重后的查询文本: {texts}")

        # 确保查询配置包含必要的返回字段
        query_config.update({"include": ["documents", "distances", "metadatas"]})
        logger.info(f"更新后的查询配置: {query_config}")

        # 如果指定了用户ID, 则通过元数据过滤
        if user_id:
            if query_config.get("where", None) is None:
                query_config["where"] = {"user_id": user_id}
            else:
                query_config["where"]["user_id"] = user_id
            logger.info(f"添加用户过滤条件: {query_config['where']}")

        try:
            # 获取嵌入向量并查询
            logger.info("获取查询文本的嵌入向量...")
            resp = await self.model.aembedding(texts, **embedding_config)
            query_embeddings = [e['embedding'] for e in resp.data]
            logger.info(f"嵌入向量维度: {len(query_embeddings[0]) if query_embeddings else 0}")
            
            logger.info("执行向量检索...")
            results = collection.query(query_embeddings=query_embeddings, **query_config)
            logger.info(f"原始检索结果数量: {len(results['ids'][0]) if results and 'ids' in results else 0}")

            # 处理每个查询的结果 - 格式化为新的返回结构
            final_results = []
            for i in range(len(texts)):
                logger.info(f"\nchroma query >>> 处理第 {i+1} 个查询结果")
                # 使用阈值过滤结果
                filtered_indices = [
                    j for j, distance in enumerate(results['distances'][i])
                    if distance < threshold
                ]
                logger.info(f"距离值: {results['distances'][i]}")
                logger.info(f"过滤后的索引: {filtered_indices}")
                
                # 构建匹配项列表
                matches = []
                for j in filtered_indices:
                    matches.append({
                        "text": results['documents'][i][j],
                        "score": results['distances'][i][j],
                        "metadata": results['metadatas'][i][j]
                    })
                
                # 添加到结果
                final_results.append({
                    "query": texts[i],
                    "results": matches
                })
                logger.info(f"过滤后的结果数量: {len(matches)}")

            return final_results
        except Exception as e:
            # 向量嵌入或检索失败时的优雅降级
            logger.error(f"向量检索失败: {str(e)}")
            logger.warning("启用降级模式：返回空结果而不是抛出异常")
            
            # 为每个查询创建空结果
            empty_results = []
            for text in texts:
                empty_result = {
                    "query": text,
                    "results": []
                }
                empty_results.append(empty_result)
            
            return empty_results
    
    async def list_collections(self) -> List[str]:
        """列出所有集合名称
        
        Returns:
            集合名称列表
        """
        try:
            collections = self.client.list_collections()
            return [collection.name for collection in collections]
        except Exception as e:
            logger.error(f"列出集合失败: {str(e)}")
            return []
    
    async def get_stats(self, collection_name: str = None) -> Dict[str, Any]:
        """获取集合统计信息
        
        Args:
            collection_name: 集合名称，为None时返回所有集合的统计信息
            
        Returns:
            统计信息字典
        """
        stats = {}
        
        try:
            if collection_name:
                # 统计单个集合
                try:
                    collection = self.client.get_collection(collection_name)
                    count = collection.count()
                    stats[collection_name] = {"total_vectors": count}
                except Exception as e:
                    stats[collection_name] = {"error": str(e)}
            else:
                # 统计所有集合
                collections = await self.list_collections()
                for coll in collections:
                    coll_stats = await self.get_stats(coll)
                    stats.update(coll_stats)
            
            return stats
        except Exception as e:
            logger.error(f"获取统计信息失败: {str(e)}")
            return {"error": str(e)}
    
    async def close(self) -> bool:
        """关闭检索器，释放资源
        
        Returns:
            操作是否成功
        """
        try:
            # 关闭嵌入模型资源
            if hasattr(self.model, 'close'):
                await self.model.close()
            
            # 关闭ChroamDB客户端
            if hasattr(self.client, 'close'):
                self.client.close()
            
            return True
        except Exception as e:
            logger.error(f"关闭检索器失败: {str(e)}")
            return False
