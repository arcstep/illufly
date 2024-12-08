from typing import List, Optional
import numpy as np
from ...core.runnable.vectordb.base import VectorDB
from ...io import Document
from ...utils import raise_invalid_params
import os

class LanceDB(VectorDB):
    """基于LanceDB的向量数据库实现
    
    LanceDB是一个基于Apache Arrow的嵌入式向量数据库，具有以下特点：
    1. 基于文件系统存储，无需额外服务
    2. 支持结构化数据和向量的联合查询
    3. 高效的数据压缩和查询性能
    4. 支持增量更新
    
    使用示例：
    ```python
    from illufly.embeddings import SomeEmbeddings
    
    # 初始化
    embeddings = SomeEmbeddings(dim=768)
    db = LanceDB(
        embeddings=embeddings,
        uri="./lance_data",           # 数据存储路径
        table_name="my_docs",         # 表名
        distance_metric="cosine"      # 距离计算方式
    )
    
    # 添加文档
    doc_id = db.add("示例文档", source="test")
    
    # 查询
    results = db.query("查询文本", top_k=3)
    
    # 结构化查询
    results = db.query(
        "查询文本",
        where="source = 'test'",  # 支持SQL WHERE子句
        top_k=3
    )
    ```
    
    Attributes:
        uri (str): LanceDB数据存储路径
        table_name (str): 表名
        distance_metric (str): 距离计算方式，支持 cosine/l2/dot
        connection (lance.LanceConnection): LanceDB连接实例
        table (lance.LanceTable): LanceDB表实例
    """
    
    @classmethod
    def allowed_params(cls):
        return {
            "uri": "LanceDB数据存储路径",
            "table_name": "表名，默认为'default'",
            "distance_metric": "距离计算方式(cosine/l2/dot)，默认为'cosine'",
            **VectorDB.allowed_params()
        }

    def __init__(
        self,
        uri: str,
        table_name: str = None,
        distance_metric: str = None,
        **kwargs
    ):
        """初始化LanceDB实例
        
        Args:
            uri: 数据存储路径
            table_name: 表名，默认为'default'
            distance_metric: 距离计算方式，默认为'cosine'
            **kwargs: 其他基类参数
        """
        raise_invalid_params(kwargs, self.__class__.allowed_params())
        
        try:
            import lancedb
            import pyarrow as pa
        except ImportError:
            raise ImportError(
                "未找到lancedb包。请通过以下命令安装：\n"
                "pip install lancedb pyarrow"
            )
        
        self.uri = uri
        self.table_name = table_name or "default"
        self.distance_metric = distance_metric or "cosine"
        
        # 确保存储目录存在
        os.makedirs(uri, exist_ok=True)
        
        # 初始化LanceDB连接
        self.connection = lancedb.connect(uri)
        
        super().__init__(**kwargs)

    def _init_index(self):
        """初始化LanceDB表"""
        import pyarrow as pa
        
        # 定义表结构
        schema = pa.schema([
            ('id', pa.string()),
            ('text', pa.string()),
            ('vector', pa.list_(pa.float32(), self.dim)),
            ('source', pa.string()),
            ('metadata', pa.string()),  # JSON格式的其他元数据
        ])
        
        # 获取或创建表
        if self.table_name in self.connection.table_names():
            self.table = self.connection.open_table(self.table_name)
        else:
            self.table = self.connection.create_table(
                self.table_name,
                schema=schema,
                mode="overwrite"
            )
            
        # 创建向量索引
        self.table.create_index(
            vector_column="vector",
            metric=self.distance_metric
        )

    def update_documents(self, docs: List[Document]) -> int:
        """更新LanceDB表
        
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
            
        import json
        import pyarrow as pa
        
        # 准备批量添加数据
        data = {
            'id': [],
            'text': [],
            'vector': [],
            'source': [],
            'metadata': []
        }
        
        for doc, vector in zip(docs, vectors):
            doc_id = doc.meta.get('id')
            if not doc_id:
                continue
                
            data['id'].append(doc_id)
            data['text'].append(doc.text)
            data['vector'].append(vector.tolist())
            data['source'].append(str(doc.meta.get('source', 'unknown')))
            
            # 其他元数据转为JSON
            metadata = {
                k: str(v) for k, v in doc.meta.items()
                if k not in ['id', 'embeddings', 'source']
            }
            data['metadata'].append(json.dumps(metadata))
        
        if not data['id']:
            return 0
            
        # 转换为Arrow表格式
        table = pa.Table.from_pydict(data)
        
        # 使用merge更新数据
        self.table.merge(table, on=['id'])
        
        return len(data['id'])

    def delete_document(self, knowledge_id: str) -> bool:
        """从LanceDB表中删除文档
        
        Args:
            knowledge_id: 要删除的文档ID
        Returns:
            bool: 是否删除成功
        """
        try:
            # 使用SQL DELETE语句
            self.table.delete(f"id = '{knowledge_id}'")
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
            **kwargs: 额外的查询参数
                - where: SQL WHERE子句，用于过滤
        Returns:
            List[Document]: 相似文档列表
        """
        if not text or len(text.strip()) == 0:
            return []
            
        actual_top_k = top_k or self.top_k or 5
        
        try:
            # 获取查询向量
            query_vector = self.embeddings.query(text)
            
            # 构建查询
            query = self.table.vector_search(
                query_vector,
                "vector",
                k=actual_top_k,
                metric=self.distance_metric
            )
            
            # 添加WHERE过滤
            if 'where' in kwargs:
                query = query.where(kwargs['where'])
            
            # 执行查询
            results = query.to_pandas()
            
            # 处理结果
            docs = []
            import json
            
            for _, row in results.iterrows():
                # 计算相似度得分
                if self.distance_metric == "cosine":
                    score = 1 - row._distance
                else:  # l2 或 dot
                    score = 1 / (1 + row._distance)
                
                if min_score is not None and score < min_score:
                    continue
                
                # 构建文档
                meta = {
                    'id': row.id,
                    'distance': float(row._distance),
                    'score': score,
                    'source': row.source
                }
                
                # 添加其他元数据
                if include_metadata:
                    try:
                        additional_meta = json.loads(row.metadata)
                        meta.update(additional_meta)
                    except:
                        pass
                
                docs.append(Document(
                    text=row.text,
                    meta=meta
                ))
            
            return docs
            
        except Exception as e:
            if self.verbose:
                print(f"查询过程中发生错误: {str(e)}")
            return []