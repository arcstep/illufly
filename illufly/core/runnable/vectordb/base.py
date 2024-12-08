from typing import List, Dict
import numpy as np
from ....io import EventBlock, BaseKnowledge, Document
from ....utils import raise_invalid_params
from ..base import Runnable
from ..embeddings import BaseEmbeddings

class VectorDB(Runnable):
    """向量数据库基类
    
    该类提供了向量数据库的通用实现框架，包括文档管理、向量处理和检索接口。
    子类可以实现不同的向量索引机制，但共享相同的文档管理和查询接口。
    
    主要功能：
    1. 文档管理：添加、更新、删除文档
    2. 向量索引：维护文档向量和索引的映射关系
    3. 相似度检索：查找与输入文本最相似的文档
    
    使用流程：
    ```python
    # 初始化向量数据库
    db = VectorDB(embeddings=embeddings_model)
    
    # 添加文档
    doc_id = db.add("文档内容", source="test")
    
    # 批量添加
    ids = db.batch_add(["文档1", "文档2"], [{"source": "test1"}, {"source": "test2"}])
    
    # 更新文档
    db.update(doc_id, "新的内容", source="updated")
    
    # 删除文档
    db.delete(doc_id)
    
    # 查询相似文档
    results = db.query("查询文本", top_k=5)
    ```
    
    子类需要实现的方法：
    - _init_index(): 初始化向量索引
    - update_documents(): 更新索引
    - delete_document(): 删除索引
    - query(): 向量检索
    
    Attributes:
        knowledge (BaseKnowledge): 文档管理器
        embeddings (BaseEmbeddings): 向量编码模型
        dim (int): 向量维度
        top_k (int): 默认返回结果数量
    """
    
    @classmethod
    def allowed_params(cls):
        return {
            "knowledge": "知识库实例",
            "embeddings": "用于相似度计算的 embeddings 对象",
            "top_k": "返回结果的条数，默认 5",
            **Runnable.allowed_params()
        }

    def __init__(self, knowledge: BaseKnowledge=None, embeddings: BaseEmbeddings=None, top_k: int=None, **kwargs):
        """初始化向量数据库
        
        Args:
            knowledge: 知识库实例
            embeddings: 文本向量化模型
            top_k: 默认返回结果数量
        """
        raise_invalid_params(kwargs, self.__class__.allowed_params())

        if not isinstance(embeddings, BaseEmbeddings):
            raise ValueError(f"{embeddings} must be an instance of BaseEmbeddings")
        if embeddings.dim is None:
            raise ValueError(f"{embeddings} dim must be set")

        super().__init__(**kwargs)

        self.knowledge = knowledge or BaseKnowledge()
        self.embeddings = embeddings
        self.top_k = top_k
        self.dim = embeddings.dim  # 确保设置维度属性
        
        # 子类需要实现_init_index和load_all_documents

    def _init_index(self):
        """初始化向量索引
        
        子类必须实现此方法来初始化特定的向量索引结构。
        """
        raise NotImplementedError()

    def _process_embeddings(self, docs: List[Document]) -> np.ndarray:
        """处理文档的向量嵌入
        
        为文档生成向量表示，并缓存在文档的meta中。
        
        Args:
            docs: 要处理的文档列表
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

    def add(self, text: str, **meta) -> str:
        """添加单个文档
        
        Args:
            text: 文档文本
            **meta: 文档元数据
        Returns:
            str: 文档ID
        """
        knowledge_id = self.knowledge.add(text, **meta)
        doc = self.knowledge.get(knowledge_id)
        self.update_documents([doc])
        return knowledge_id

    def update_documents(self, docs: List[Document]) -> int:
        """更新向量索引
        
        子类必须实现此方法来维护文档ID与向量的映射关系。
        
        Args:
            docs: 要更新的文档列表
        Returns:
            int: 成功更新的文档数量
        """
        raise NotImplementedError()

    def delete_document(self, knowledge_id: str) -> bool:
        """从向量索引中删除文档
        
        子类必须实现此方法来清理文档ID与向量的映射关系。
        
        Args:
            knowledge_id: 要删除的文档ID
        Returns:
            bool: 是否删除成功
        """
        raise NotImplementedError()

    def query(
        self, 
        text: str, 
        top_k: int = None, 
        min_score: float = None,
        include_metadata: bool = True,
        **kwargs
    ) -> List[Document]:
        """查询相似文档
        
        子类必须实现此方法来执行向量检索。
        
        Args:
            text: 查询文本
            top_k: 返回结果数量
            min_score: 最小相似度阈值
            include_metadata: 是否包含完整元数据
            **kwargs: 额外的查询参数
        Returns:
            List[Document]: 相似文档列表
        """
        raise NotImplementedError()

    def _process_query_results(
        self,
        docs: List[Document],
        distances: np.ndarray = None,
        scores: np.ndarray = None,
        min_score: float = None,
        include_metadata: bool = True
    ) -> List[Document]:
        """处理查询结果
        
        标准化查询结果的格式，添加距离和得分信息。
        子类可以选择使用或重写此方法。
        
        Args:
            docs: 匹配的文档列表
            distances: 向量距离数组，可选
            scores: 相似度得分数组，可选
            min_score: 最小相似度阈值
            include_metadata: 是否包含完整元数据
        Returns:
            List[Document]: 处理后的文档列表
        """
        results = []
        for i, doc in enumerate(docs):
            # 构建基础元数据
            meta = {'id': doc.meta['id']}
            
            # 添加距离和得分信息
            if distances is not None:
                meta['distance'] = float(distances[i])
            if scores is not None:
                meta['score'] = float(scores[i])
                if min_score is not None and meta['score'] < min_score:
                    continue
            
            # 添加其他元数据
            if include_metadata:
                meta.update({
                    k: v for k, v in doc.meta.items()
                    if k not in ['embeddings', 'id', 'distance', 'score']
                })
            
            results.append(Document(text=doc.text, meta=meta))
        
        # 按得分排序（如果有）
        if scores is not None:
            results.sort(key=lambda x: x.meta.get('score', 0), reverse=True)
        
        return results

    def call(self, text: str, top_k: int=None, **kwargs):
        self._last_output = self.query(text, top_k or self.top_k or 5, **kwargs)
        yield EventBlock("info", f"查询到{len(self._last_output)}条结果")

    def load_all_documents(self):
        """初始化时加载知识库中的所有文档到向量索引
        
        从知识库加载所有文档，并更新向量索引。
        子类需要实现 _load_documents_to_index 方法来处理具体的索引更新。
        """
        docs = self.knowledge.all()
        if not docs:
            return
        
        # 确保所有文档的source字段存在且为字符串
        for doc in docs:
            if 'source' not in doc.meta:
                doc.meta['source'] = 'unknown'
            else:
                doc.meta['source'] = str(doc.meta['source'])
        
        # 更新向量索引
        self.update_documents(docs)

    def rebuild_index(self):
        """重建向量索引
        
        清空当前索引并重新加载所有文档。
        子类可以重写此方法来实现更高效的重建策略。
        """
        self._init_index()  # 重新初始化索引
        self.load_all_documents()  # 重新加载所有文档