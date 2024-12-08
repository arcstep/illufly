from typing import List, Union, Callable
from ...utils import raise_invalid_params
from ...types import VectorDB
from ...io import BaseKnowledge, Document

import numpy as np

class FaissDB(VectorDB):
    """FaissCPU向量数据库
    
    该类实现了基于Faiss的向量检索功能，与BaseKnowledge配合使用。
    
    主要功能：
    1. 文档向量的添加、更新、删除
    2. 向量相似度检索
    3. 与知识库的同步管理
    4. 批量操作支持
    
    注意事项：
    1. 所有文档操作都应先在知识库(BaseKnowledge)中执行，再更新向量索引
    2. Faiss不支持真正删除向量，删除操作只是标记位置无效
    3. 大量更新或删除后建议重建索引以优化性能
    4. 提供快捷方法自动处理知识库和向量索引的同步
    
    基本使用流程：
    ```python
    # 初始化（自动创建知识库）
    faiss_db = FaissDB(dim=768)
    
    # 添加单个文档
    kid1 = faiss_db.add("第一个文档", source="test")
    kid2 = faiss_db.add("第二个文档", source="test")
    
    # 批量添加文档
    texts = ["文档3", "文档4"]
    metas = [{"source": "batch1"}, {"source": "batch2"}]
    kids = faiss_db.batch_add(texts, metas)
    
    # 更新文档
    faiss_db.update(kid1, text="更新后的文档")
    faiss_db.update(kid2, source="updated")  # 只更新元数据
    
    # 删除文档
    faiss_db.delete(kid1)
    faiss_db.batch_delete([kid2, kids[0]])
    
    # 查询相似文档
    results = faiss_db.query("查询文本", top_k=5)
    
    # 优化索引（在大量更新/删除后调用）
    faiss_db.rebuild_index()
    ```
    
    高级用法（直接操作知识库）：
    ```python
    # 使用自定义知识库
    knowledge = BaseKnowledge()
    faiss_db = FaissDB(knowledge=knowledge, dim=768)
    
    # 手动管理知识库和向量索引
    # 添加文档
    kid = knowledge.add("新文档")
    doc = knowledge.get(kid)
    faiss_db.update_documents([doc])
    
    # 更新文档
    knowledge.update(kid, text="更新内容")
    updated_doc = knowledge.get(kid)
    faiss_db.update_document(updated_doc)
    
    # 删除文档
    knowledge.delete(kid)
    faiss_db.delete_document(kid)
    ```
    
    方法说明：
    - 快捷方法（推荐使用）：
        - add(): 添加单个文档
        - batch_add(): 批量添加文档
        - update(): 更新文档
        - delete(): 删除文档
        - batch_delete(): 批量删除文档
        - query(): 查询相似文档
        - rebuild_index(): 重建索引
        
    - 内部方法（用于手动控制）：
        - update_documents(): 更新向量索引
        - update_document(): 更新单个文档的向量
        - delete_document(): 删除向量索引
        - load_all_documents(): 加载所有文档
        - _process_embeddings(): 处理文档向量
    """

    @classmethod
    def allowed_params(cls):
        return {
            "train": "是否在加载数据时训练模型，默认为True",
            "knowledge": "绑定的BaseKnowledge实例，用于文档管理",
            **VectorDB.allowed_params()
        }

    def __init__(self, knowledge: BaseKnowledge = None, train: bool = None, **kwargs):
        """初始化FaissDB实例
        
        Args:
            knowledge: BaseKnowledge实例，用于文档管理。若不提供则自动创建
            train: 是否在加载数据时训练模型，默认为True
            **kwargs: 其他参数，见allowed_params
        """
        raise_invalid_params(kwargs, self.__class__.allowed_params())
        super().__init__(**kwargs)
        
        self.knowledge = knowledge if knowledge is not None else BaseKnowledge()
        self.train = train if train is not None else True
        
        try:
            import faiss
        except ImportError:
            raise ImportError(
                "未找到faiss包。请通过以下命令安装：\n"
                "pip install -U faiss-cpu faiss-gpu"
            )
        
        self.index = faiss.IndexFlatL2(self.dim)
        self.id_to_index = {}
        self.index_to_id = {}
        self.load_all_documents()

    def load_all_documents(self):
        """初始化时加载知识库中的所有文档到向量索引"""
        docs = self.knowledge.all()
        if not docs:
            return
            
        # 确保所有文档的source字段存在且为字符串
        for doc in docs:
            if 'source' not in doc.meta:
                doc.meta['source'] = 'unknown'
            else:
                doc.meta['source'] = str(doc.meta['source'])
        
        vectors = self._process_embeddings(docs)
        if vectors is not None and len(vectors) > 0:
            if self.train:
                self.index.train(vectors)
            self.index.add(vectors)
            
            for i, doc in enumerate(docs):
                knowledge_id = doc.meta.get('id')
                if knowledge_id:
                    self.id_to_index[knowledge_id] = i
                    self.index_to_id[i] = knowledge_id

    def _process_embeddings(self, docs: List[Document]) -> np.ndarray:
        """处理文档的向量嵌入
        
        Args:
            docs: 文档列表
        Returns:
            np.ndarray: 文档向量数组，shape为(n_docs, dim)
        """
        if not docs:
            return None
            
        not_embedded_docs = [d for d in docs if 'embeddings' not in d.meta]
        if not_embedded_docs:
            new_embeddings = self.embeddings(not_embedded_docs, verbose=self.verbose)
            for doc, new_doc in zip(not_embedded_docs, new_embeddings):
                doc.meta['embeddings'] = new_doc.meta['embeddings']
        
        vectors = [d.meta['embeddings'] for d in docs]
        return np.array(vectors, dtype='float32')

    def rebuild_index(self):
        """重建向量索引
        
        在大量更新或删除操作后调用，用于优化索引结构
        """
        import faiss
        self.id_to_index.clear()
        self.index_to_id.clear()
        self.index = faiss.IndexFlatL2(self.dim)
        self.load_all_documents()

    def update_documents(self, docs: List[Document]) -> int:
        """批量更新向量索引
        
        Args:
            docs: 文档列表，每个文档必须包含id
        Returns:
            int: 成功更新的文档数量
        """
        vectors = self._process_embeddings(docs)
        if vectors is None or len(vectors) == 0:
            return 0
            
        current_index = len(self.id_to_index)
        if self.train:
            self.index.train(vectors)
        self.index.add(vectors)
        
        success_count = 0
        for i, doc in enumerate(docs):
            knowledge_id = doc.meta.get('id')
            if knowledge_id:
                self.id_to_index[knowledge_id] = current_index + i
                self.index_to_id[current_index + i] = knowledge_id
                success_count += 1
        
        return success_count

    def add(self, text: str, **meta) -> str:
        """添加新文档的快捷方法
        
        自动处理知识库添加和向量索引��新
        
        Args:
            text: 文档文本
            **meta: 文档元数据
        Returns:
            str: 新文档的knowledge_id
        """
        # 添加到知识库
        knowledge_id = self.knowledge.add(text, **meta)
        doc = self.knowledge.get(knowledge_id)
        
        # 更新向量索引
        self.update_documents([doc])
        return knowledge_id

    def batch_add(self, texts: List[str], metas: List[dict] = None) -> List[str]:
        """批量添加文档的快捷方法
        
        Args:
            texts: 文档文本列表
            metas: 文档元数据列表，可选
        Returns:
            List[str]: 新文档的knowledge_id列表
        """
        if metas is None:
            metas = [{} for _ in texts]
        
        # 批量添加到知识库
        knowledge_ids = [
            self.knowledge.add(text, **meta)
            for text, meta in zip(texts, metas)
        ]
        
        # 获取文档并更新向量索引
        docs = [self.knowledge.get(kid) for kid in knowledge_ids]
        self.update_documents(docs)
        return knowledge_ids

    def update(self, knowledge_id: str, text: str = None, **meta) -> bool:
        """更新文档的快捷方法
        
        Args:
            knowledge_id: 文档ID
            text: 新的文档文本，可选
            **meta: 要更新的元数据
        Returns:
            bool: 更新是否成功
        """
        # 更新知识库
        if not self.knowledge.update(knowledge_id, text, **meta):
            return False
        
        # 更新向量索引
        doc = self.knowledge.get(knowledge_id)
        return self.update_document(doc)

    def delete(self, knowledge_id: str) -> bool:
        """删除文档的快捷方法
        
        Args:
            knowledge_id: 要删除的文档ID
        Returns:
            bool: 删除是否成功
        """
        # 先从知识库删除
        if not self.knowledge.delete(knowledge_id):
            return False
        
        # 再清理向量索引
        return self.delete_document(knowledge_id)

    def batch_delete(self, knowledge_ids: List[str]) -> int:
        """批量删除文档的快捷方法
        
        Args:
            knowledge_ids: 要删除的文档ID列表
        Returns:
            int: 成功删除的文档数量
        """
        success_count = 0
        for kid in knowledge_ids:
            if self.delete(kid):
                success_count += 1
        
        # 如果删除了大量文档，自动重建索引
        if success_count > 1000:  # 可以根据需要调整阈值
            self.rebuild_index()
        
        return success_count

    def delete_document(self, knowledge_id: str) -> bool:
        """删除文档的向量索引
        
        注意：此方法仅处理向量索引的删除，不处理知识库。
        由于Faiss不支持真正删除向量，这里只是标记位置无效。
        如果需要真正删除，请使用 delete() 方法或在大量删除后调用 rebuild_index()。
        
        Args:
            knowledge_id: 要删除的文档ID
        Returns:
            bool: 删除是否成功
        """
        if knowledge_id in self.id_to_index:
            index_position = self.id_to_index[knowledge_id]
            del self.id_to_index[knowledge_id]
            del self.index_to_id[index_position]
            return True
        return False

    def query(
        self, 
        text: str, 
        top_k: int = None, 
        min_score: float = None,
        include_metadata: bool = True,
        **kwargs
    ) -> List[Document]:
        """查询与输入文本最相似的文档
        
        Args:
            text: 查询文本
            top_k: 返回结果数量，默认使用实例的 top_k 参数
            min_score: 最小相似度阈值，小于该值的结果将被过滤
            include_metadata: 是否在结果中包含完整的元数据
            **kwargs: 额外的查询参数
        
        Returns:
            List[Document]: 相似文档列表，按相似度降序排序
            每个文档的meta中会添加:
            - distance: 向量距离（越小表示越相似）
            - score: 相似度得分（1 - normalized_distance，越大表示越相似）
        """
        # 参数检查
        if len(self.id_to_index) == 0:
            return []
        if not text or len(text.strip()) == 0:
            return []
        
        actual_top_k = top_k or self.top_k or 5
        
        try:
            # 对输入文本进行向量编码
            query_vector = self.embeddings.query(text)
            if not isinstance(query_vector, np.ndarray):
                query_vector = np.array([query_vector], dtype='float32')
            
            # 执行向量检索
            distances, indices = self.index.search(query_vector, actual_top_k)
            
            # 处理检索结果
            results = []
            max_distance = float(distances.max()) if len(distances) > 0 else 1.0
            
            for i, idx in enumerate(indices[0]):
                if idx < 0:  # 跳过无效索引
                    continue
                    
                knowledge_id = self.index_to_id.get(idx)
                if not knowledge_id:
                    continue
                    
                doc = self.knowledge.get(knowledge_id)
                if not doc:
                    continue
                
                # 计算归一化的距离和相似度得分
                distance = float(distances[0][i])
                score = 1 - (distance / max_distance) if max_distance > 0 else 0
                
                # 如果设置了最小得分阈值，进行过滤
                if min_score is not None and score < min_score:
                    continue
                
                # 构建结果文档
                meta = {
                    'id': knowledge_id,
                    'distance': distance,
                    'score': score
                }
                
                # 根据需要包含原始元数据
                if include_metadata:
                    meta.update({
                        k: v for k, v in doc.meta.items()
                        if k not in ['embeddings', 'id', 'distance', 'score']
                    })
                
                results.append(Document(
                    text=doc.text,
                    meta=meta
                ))
            
            # 按相似度得分降序排序
            results.sort(key=lambda x: x.meta['score'], reverse=True)
            return results
            
        except Exception as e:
            if self.verbose:
                print(f"查询过程中发生错误: {str(e)}")
            return []

