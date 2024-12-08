from typing import List, Optional
import numpy as np
from ...core.runnable.vectordb.base import VectorDB
from ...io import Document
from ...utils import raise_invalid_params

class ChromaDB(VectorDB):
    """基于ChromaDB的向量数据库实现
    
    ChromaDB是一个开源的向量数据库，具有以下特点：
    1. 使用UUID作为向量ID
    2. 支持元数据过滤
    3. 内置多种距离计算方式
    4. 支持持久化存储
    
    使用示例：
    ```python
    from illufly.rag import ChromaDB, TextEmbeddings
    
    # 初始化
    embeddings = TextEmbeddings(dim=768)
    db = ChromaDB(
        embeddings=embeddings,
        persist_directory="./chroma_db",  # 持久化目录
        collection_name="my_docs",        # 集合名称
        distance_func="cosine"            # 距离计算方式
    )
    
    # 添加文档
    doc_id = db.add("示例文档", source="test")
    
    # 查询
    results = db.query("查询文本", top_k=3)
    ```
    
    Attributes:
        collection_name (str): ChromaDB集合名称
        distance_func (str): 距离计算方式，支持 cosine/l2/ip
        client (chromadb.Client): ChromaDB客户端实例
        collection (chromadb.Collection): ChromaDB集合实例
    """
    
    @classmethod
    def allowed_params(cls):
        return {
            "persist_directory": "ChromaDB持久化目录路径",
            "collection_name": "集合名称，默认为'default'",
            "distance_func": "距离计算方式(cosine/l2/ip)，默认为'cosine'",
            **VectorDB.allowed_params()
        }

    def __init__(
        self,
        persist_directory: str,
        collection_name: str = None,
        distance_func: str = None,
        **kwargs
    ):
        """初始化ChromaDB实例"""
        # 1. 参数验证
        raise_invalid_params(kwargs, self.__class__.allowed_params())
        
        # 2. 依赖检查
        try:
            import chromadb
        except ImportError:
            raise ImportError("请安装chromadb")
        
        # 3. 调用父类初始化，获取embeddings和dim
        super().__init__(**kwargs)
        
        # 4. 设置基本属性
        self.persist_directory = persist_directory
        self.collection_name = collection_name or "default"
        self.distance_func = distance_func or "cosine"
        
        # 5. 初始化客户端
        self.client = chromadb.PersistentClient(path=persist_directory)
        
        # 6. 初始化集合
        self._init_index()

    def _init_index(self):
        """初始化ChromaDB集合"""
        # 获取或创建集合
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": self.distance_func}
        )

    def update_documents(self, docs: List[Document]) -> int:
        """更新ChromaDB集合
        
        Args:
            docs: 要更新的文档列表
        Returns:
            int: 成功更新的文档数量
        """
        if not docs:
            return 0
            
        # 处理向量
        vectors = self._process_embeddings(docs)
        if vectors is None:
            return 0
            
        # 准备批量添加数据
        ids = []
        texts = []
        metadatas = []
        embeddings = []
        
        for doc, vector in zip(docs, vectors):
            doc_id = doc.meta.get('id')
            if not doc_id:
                continue
                
            ids.append(doc_id)
            texts.append(doc.text)
            
            # 过滤元数据
            metadata = {
                k: str(v) for k, v in doc.meta.items()
                if k not in ['id', 'embeddings']
            }
            metadatas.append(metadata)
            embeddings.append(vector)
        
        if not ids:
            return 0
            
        # 使用upsert添加或更新文档
        self.collection.upsert(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=embeddings
        )
        
        return len(ids)

    def delete_document(self, knowledge_id: str) -> bool:
        """从ChromaDB集合中删除文档
        
        Args:
            knowledge_id: 要删除的文档ID
        Returns:
            bool: 是否删除成功
        """
        try:
            self.collection.delete(ids=[knowledge_id])
            return True
        except Exception as e:
            if self.verbose:
                print(f"删除文档时出错: {str(e)}")
            return False

    def query(
        self, 
        text: str, 
        top_k: int = None, 
        min_score: float = None,
        include_metadata: bool = True,
        **kwargs
    ) -> List[Document]:
        """查询相似文档
        
        Args:
            text: 查询文本
            top_k: 返回结果数量
            min_score: 最小相似度阈值
            include_metadata: 是否包含完整元数据
            **kwargs: 额外的查询参数，支持ChromaDB的where过滤
        Returns:
            List[Document]: 相似文档列表
        """
        if not text or len(text.strip()) == 0:
            return []
            
        actual_top_k = top_k or self.top_k or 5
        
        try:
            # 获取查询向量
            query_vector = self.embeddings.query(text)
            
            # 执行查询
            results = self.collection.query(
                query_embeddings=[query_vector],
                n_results=actual_top_k,
                where=kwargs.get('where'),  # 支持元数据过滤
                include=['documents', 'metadatas', 'distances']
            )
            
            # 处理结果
            docs = []
            for i in range(len(results['ids'][0])):
                doc_id = results['ids'][0][i]
                distance = float(results['distances'][0][i])
                
                # 计算相似度得分
                if self.distance_func == "cosine":
                    score = 1 - distance
                else:  # l2 或 ip
                    score = 1 / (1 + distance)
                
                if min_score is not None and score < min_score:
                    continue
                
                # 构建文档
                meta = {
                    'id': doc_id,
                    'distance': distance,
                    'score': score
                }
                
                if include_metadata:
                    meta.update(results['metadatas'][0][i])
                
                docs.append(Document(
                    text=results['documents'][0][i],
                    meta=meta
                ))
            
            return docs
            
        except Exception as e:
            if self.verbose:
                print(f"查询过程中发生错误: {str(e)}")
            return []

    def rebuild_index(self):
        """重建ChromaDB集合
        
        删除并重新创建集合，然后重新加载所有文档。
        """
        try:
            # 删除现有集合
            if self.collection_name in self.client.list_collections():
                self.client.delete_collection(self.collection_name)
            
            # 重新初始化集合
            self._init_index()
            
            # 重新加载所有文档
            self.load_all_documents()
            
            if self.verbose:
                print(f"成功重建集合 {self.collection_name}")
                
        except Exception as e:
            if self.verbose:
                print(f"重建索引时出错: {str(e)}")
            raise