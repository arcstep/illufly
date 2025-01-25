from typing import List, Optional
from datetime import datetime

class ConceptStorage:
    def __init__(self):
        self.vector_store = VectorStore()
        self.db = RocksDBWrapper()
        
    async def store_concept(self, layer: int, concept: Any):
        """存储概念到指定层"""
        # 存储向量表示
        vector = await self.vector_store.encode(concept)
        await self.vector_store.store(f"layer_{layer}", vector)
        
        # 存储原始内容
        key = f"l{layer}:{datetime.now().isoformat()}"
        await self.db.put(key, concept)
        
    async def find_similar_concepts(self, concept: Any, layer: int, 
                                  threshold: float = 0.85) -> List[Any]:
        """查找相似概念"""
        vector = await self.vector_store.encode(concept)
        similar_vectors = await self.vector_store.search(
            f"layer_{layer}",
            vector,
            threshold
        )
        return [
            await self.db.get(vec.id)
            for vec in similar_vectors
        ]

class ProcessingError(Exception):
    """处理错误异常"""
    pass

class ConceptRetriever:
    async def retrieve(self, query, context=None):
        results = []
        # 从高层到低层查询
        for level in reversed(range(len(LAYER_CONFIGS))):
            layer_results = await self.storage.find_similar_concepts(
                query,
                level,
                LAYER_CONFIGS[level]["similarity_threshold"]
            )
            if layer_results:
                results.extend(layer_results)
                # 可以根据需要决定是否继续查询低层
                if context and context.get("deep_search") is False:
                    break
        return results