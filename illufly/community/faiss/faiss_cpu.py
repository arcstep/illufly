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
    
    注意事项：
    1. 所有文档操作都应先在知识库(BaseKnowledge)中执行，再更新向量索引
    2. Faiss不支持真正删除向量，删除操作只是标记位置无效
    3. 大量更新后建议重建索引以优化性能
    
    基本使用流程：
    ```python
    # 初始化
    knowledge = BaseKnowledge()
    faiss_db = FaissDB(knowledge=knowledge, dim=768)
    
    # 添加文档
    knowledge_id = knowledge.add("新文档")
    doc = knowledge.get(knowledge_id)
    faiss_db.update_documents([doc])
    
    # 更新文档
    knowledge.update(knowledge_id, text="更新的内容")
    updated_doc = knowledge.get(knowledge_id)
    faiss_db.update_document(updated_doc)
    
    # 删除文档
    knowledge.delete(knowledge_id)
    faiss_db.delete_document(knowledge_id)
    
    # 查询相似文档
    results = faiss_db.query("查询文本", top_k=5)
    ```
    """

    @classmethod
    def allowed_params(cls):
        return {
            "train": "是否在加载数据时训练模型，默认为True",
            "knowledge": "绑定的BaseKnowledge实例，用于文档管理",
            **VectorDB.allowed_params()
        }

    def __init__(self, knowledge: BaseKnowledge, train: bool = None, **kwargs):
        """初始化FaissDB实例
        
        Args:
            knowledge: BaseKnowledge实例，用于文档管理
            train: 是否在加载数据时训练模型，默认为True
            **kwargs: 其他参数，见allowed_params
        """
        raise_invalid_params(kwargs, self.__class__.allowed_params())
        super().__init__(**kwargs)

        if not isinstance(knowledge, BaseKnowledge):
            raise TypeError("knowledge 必须是 BaseKnowledge 实例")
        
        try:
            import faiss
        except ImportError:
            raise ImportError(
                "未找到faiss包。请通过以下命令安装：\n"
                "pip install -U faiss-cpu faiss-gpu"
            )

        self.knowledge = knowledge
        self.train = train if train is not None else True
        self.index = faiss.IndexFlatL2(self.dim)
        
        # 维护knowledge_id和索引位置的双向映射
        self.id_to_index = {}  # {knowledge_id: index_position}
        self.index_to_id = {}  # {index_position: knowledge_id}
        
        self.load_all_documents()
    
    def load_all_documents(self):
        """初始化时加载知识库中的所有文档到向量索引"""
        docs = self.knowledge.all()
        if not docs:
            return
            
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

