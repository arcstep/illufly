from typing import List
from ...utils import raise_invalid_params
from ...types import VectorDB
from ...io import Document

import numpy as np

class FaissDB(VectorDB):
    """基于Faiss的向量数据库实现
    
    支持CPU和GPU两种模式，可以通过device参数控制。
    
    使用示例:
    ```python
    from illufly.rag import FaissDB, TextEmbeddings
    
    # CPU模式
    db = FaissDB(embeddings=embeddings)
    
    # GPU模式
    db = FaissDB(
        embeddings=TextEmbeddings(),
        device="cuda:0",    # 使用第一张GPU
        batch_size=1024     # GPU批处理大小
    )
    
    # 多GPU模式
    db = FaissDB(
        embeddings=TextEmbeddings(),
        device="cuda",      # 使用所有可用GPU
        gpu_devices=[0,1],  # 指定使用的GPU
        batch_size=1024
    )
    ```
    """
    
    @classmethod
    def allowed_params(cls):
        return {
            "train": "是否训练索引，默认True",
            "device": "运行设备(cpu/cuda/cuda:0等)，默认cpu",
            "gpu_devices": "指定使用的GPU设备列表，如[0,1]",
            "batch_size": "GPU模式下的批处理大小，默认1024",
            **VectorDB.allowed_params()
        }

    def __init__(
        self,
        train: bool = True,
        device: str = "cpu",
        gpu_devices: List[int] = None,
        batch_size: int = 1024,
        **kwargs
    ):
        """初始化FaissDB实例"""
        # 1. 参数验证
        raise_invalid_params(kwargs, self.__class__.allowed_params())
        
        # 2. 依赖检查
        try:
            import faiss
        except ImportError:
            pkg = "faiss-gpu" if device.startswith("cuda") else "faiss-cpu"
            raise ImportError(f"请安装{pkg}")
        
        # 3. 调用父类初始化，获取embeddings和dim
        super().__init__(**kwargs)
        
        # 4. 设置基本属性
        self.train = train
        self.device = device
        self.batch_size = batch_size
        self.gpu_devices = gpu_devices or []
        
        # 5. 初始化ID映射
        self.id_to_index = {}
        self.index_to_id = {}
        
        # 6. 初始化索引
        self._init_index()

    def _init_index(self):
        """初始化Faiss索引"""
        import faiss
        
        # 创建基础索引
        self.index = faiss.IndexFlatL2(self.dim)
        
        # GPU相关设置
        if self.device.startswith("cuda"):
            if ":" in self.device:  # 单GPU
                gpu_id = int(self.device.split(":")[-1])
                res = faiss.StandardGpuResources()
                self.index = faiss.index_cpu_to_gpu(res, gpu_id, self.index)
            else:  # 多GPU
                if self.gpu_devices:
                    co = faiss.GpuMultipleClonerOptions()
                    co.shard = True  # 在GPU间分片
                    self.index = faiss.index_cpu_to_gpu_multiple_py(
                        self.gpu_devices, 
                        self.index,
                        co
                    )
                else:  # 使用所有可用GPU
                    self.index = faiss.index_cpu_to_all_gpus(self.index)

    def _batch_search(self, query_vector: np.ndarray, k: int) -> tuple:
        """分批执行搜索，用于GPU模式"""
        if not self.device.startswith("cuda"):
            return self.index.search(query_vector, k)
            
        # GPU模式下分批处理
        n = len(query_vector)
        all_distances = []
        all_indices = []
        
        for i in range(0, n, self.batch_size):
            batch = query_vector[i:i + self.batch_size]
            distances, indices = self.index.search(batch, k)
            all_distances.append(distances)
            all_indices.append(indices)
            
        return (
            np.concatenate(all_distances),
            np.concatenate(all_indices)
        ) 

    def update_documents(self, docs: List[Document]) -> int:
        """更新Faiss索引
        
        Args:
            docs: 要更新的文档列表
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

    def delete_document(self, knowledge_id: str) -> bool:
        """从Faiss索引中删除文档
        
        Args:
            knowledge_id: 要删除的文档ID
        Returns:
            bool: 是否删除成功
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
        """查询相似文档
        
        Args:
            text: 查询文本
            top_k: 返回结果数量
            min_score: 最小相似度阈值
            include_metadata: 是否包含完整元数据
            **kwargs: 额外的查询参数
        Returns:
            List[Document]: 相似文档列表
        """
        if len(self.id_to_index) == 0 or not text or len(text.strip()) == 0:
            return []
            
        actual_top_k = top_k or self.top_k or 5
        
        try:
            # 获取查询向量
            query_vector = self.embeddings.query(text)
            if not isinstance(query_vector, np.ndarray):
                query_vector = np.array([query_vector], dtype='float32')
            
            # 执行向量检索
            distances, indices = self._batch_search(query_vector, actual_top_k)
            
            # 获取匹配的文档
            docs = []
            for idx in indices[0]:
                if idx in self.index_to_id:
                    doc_id = self.index_to_id[idx]
                    doc = self.knowledge.get(doc_id)
                    if doc:
                        docs.append(doc)
            
            # 处理结果
            return self._process_query_results(
                docs,
                distances=distances[0][:len(docs)],
                min_score=min_score,
                include_metadata=include_metadata
            )
            
        except Exception as e:
            if self.verbose:
                print(f"查询过程中发生错误: {str(e)}")
            return []

    def rebuild_index(self):
        """重建Faiss索引
        
        由于Faiss不支持真正的删除操作，频繁的删除会导致索引碎片化，
        定期重建索引可以优化性能和内存使用。
        
        重建过程：
        1. 清空现有的索引和ID映射
        2. 重新初始化索引结构
        3. 重新加载所有文档
        """
        try:
            # 清空ID映射
            self.id_to_index.clear()
            self.index_to_id.clear()
            
            # 重新初始化索引
            self._init_index()
            
            # 重新加载所有文档
            self.load_all_documents()
            
            if self.verbose:
                print("成功重建Faiss索引")
                
        except Exception as e:
            if self.verbose:
                print(f"重建索引时出错: {str(e)}")
            raise