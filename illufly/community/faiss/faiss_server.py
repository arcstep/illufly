from typing import List
from ...utils import raise_invalid_params
from ...types import VectorDB
from ...io import Document

import numpy as np

class FaissServer(VectorDB):
    """基于Faiss服务器的向量数据库实现
    
    通过HTTP/gRPC与远程Faiss服务器通信。
    
    使用示例:
    ```python
    db = FaissServer(
        embeddings=embeddings,
        server_url="http://faiss-server:8080",
        api_key="your-api-key"
    )
    ```
    """
    
    @classmethod
    def allowed_params(cls):
        return {
            "server_url": "Faiss服务器地址",
            "api_key": "API密钥",
            "timeout": "请求超时时间(秒)",
            **VectorDB.allowed_params()
        }

    def __init__(
        self,
        server_url: str,
        api_key: str = None,
        timeout: int = 30,
        **kwargs
    ):
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        
        # 初始化HTTP客户端
        import httpx
        self.client = httpx.Client(
            base_url=self.server_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else None
        )
        
        super().__init__(**kwargs)

    def _init_index(self):
        """验证服务器连接"""
        try:
            resp = self.client.get("/health")
            resp.raise_for_status()
        except Exception as e:
            raise ConnectionError(f"无法连接到Faiss服务器: {e}")

    def update_documents(self, docs: List[Document]) -> int:
        """通过API更新向量"""
        vectors = self._process_embeddings(docs)
        if vectors is None:
            return 0
            
        data = {
            "vectors": vectors.tolist(),
            "ids": [doc.meta['id'] for doc in docs if 'id' in doc.meta]
        }
        
        try:
            resp = self.client.post("/vectors", json=data)
            resp.raise_for_status()
            return len(data["ids"])
        except Exception as e:
            if self.verbose:
                print(f"更新向量时出错: {e}")
            return 0

    def query(self, text: str, top_k: int = None, **kwargs) -> List[Document]:
        """通过API查询向量"""
        query_vector = self.embeddings.query(text)
        
        data = {
            "vector": query_vector.tolist(),
            "k": top_k or self.top_k or 5,
            **kwargs
        }
        
        try:
            resp = self.client.post("/search", json=data)
            resp.raise_for_status()
            results = resp.json()
            
            # 处理结果
            return self._process_query_results(
                results["documents"],
                distances=results.get("distances"),
                scores=results.get("scores")
            )
        except Exception as e:
            if self.verbose:
                print(f"查询时出错: {e}")
            return [] 