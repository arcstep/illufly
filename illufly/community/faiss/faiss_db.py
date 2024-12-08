from typing import List
from ...utils import raise_invalid_params
from ...types import VectorDB

import numpy as np

class FaissDB(VectorDB):
    """基于Faiss的向量数据库实现
    
    支持CPU和GPU两种模式，可以通过device参数控制。
    
    使用示例:
    ```python
    # CPU模式
    db = FaissDB(embeddings=embeddings)
    
    # GPU模式
    db = FaissDB(
        embeddings=embeddings,
        device="cuda:0",    # 使用第一张GPU
        batch_size=1024     # GPU批处理大小
    )
    
    # 多GPU模式
    db = FaissDB(
        embeddings=embeddings,
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
        train: bool = None,
        device: str = "cpu",
        gpu_devices: List[int] = None,
        batch_size: int = 1024,
        **kwargs
    ):
        self.train = train if train is not None else True
        self.device = device
        self.gpu_devices = gpu_devices
        self.batch_size = batch_size
        self.id_to_index = {}
        self.index_to_id = {}
        
        try:
            if device.startswith("cuda"):
                import faiss
                assert faiss.get_num_gpus() > 0, "No GPU found"
            else:
                import faiss
        except ImportError:
            pkg = "faiss-gpu" if device.startswith("cuda") else "faiss-cpu"
            raise ImportError(f"请安装{pkg}")
            
        super().__init__(**kwargs)

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