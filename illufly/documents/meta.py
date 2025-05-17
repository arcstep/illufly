from pathlib import Path
from typing import Dict, Any, Optional, List
import aiofiles
import json
import logging
import time
from pydantic import BaseModel, Field

from voidring import IndexedRocksDB

class DocumentMeta(BaseModel):
    """简化的文档元数据模型"""
    document_id: str = Field(..., description="文档ID")
    user_id: str = Field(..., description="用户ID")
    topic_path: Optional[str] = Field(default=None, description="主题路径")
    original_name: Optional[str] = Field(default=None, description="原始文件名")
    size: int = Field(default=0, description="文件大小")
    type: Optional[str] = Field(default=None, description="文件类型")
    extension: Optional[str] = Field(default=None, description="文件扩展名")
    source_type: Optional[str] = Field(default="local", description="来源类型")
    source_url: Optional[str] = Field(default=None, description="来源URL")
    created_at: float = Field(default_factory=time.time, description="创建时间")
    updated_at: float = Field(default_factory=time.time, description="更新时间")
    processed: bool = Field(default=False, description="是否已处理完成")
    process_error: Optional[str] = Field(default=None, description="处理失败的错误信息")
    collection_name: Optional[str] = Field(default=None, description="向量集合名称")
    is_public: bool = Field(default=False, description="是否公开共享")
    allowed_roles: List[str] = Field(default_factory=list, description="允许访问的角色列表")
    summary: Optional[str] = Field(default=None, description="文档摘要")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="用户自定义元数据")
    
    # 保留一些必要方法
    @classmethod
    def get_prefix(cls, user_id: str = None) -> str:
        """获取rocksdb键前缀"""
        user_id = user_id or "default"
        return f"doc:{user_id}"

    @classmethod
    def get_db_key(cls, user_id: str, document_id: str) -> str:
        """获取rocksdb存储键"""
        return f"{cls.get_prefix(user_id)}:{document_id}"

class DocumentMetaManager:
    """简化版文档元数据管理器 - 使用RocksDB高效管理元数据，文件系统管理实际文件
    
    关键概念:
    1. 文档(Document) - 由document_id唯一标识的内容实体，可以是本地上传文件、网页书签
    
    2. 处理状态(Processed) - 文档是否已完成处理:
       - processed=False: 未处理或处理失败
       - processed=True: 处理完成
    
    典型文档处理流程:
    1. 文档上传/保存 -> 创建元数据(processed=False)
    2. 处理文档 -> 执行转换、切片、向量化
    3. 处理完成 -> 更新元数据(processed=True)
    """
    
    __COLLECTION_NAME__ = "document_meta"
    
    def __init__(self, meta_dir: str, docs_dir: str):
        # 确保meta_dir目录存在
        Path(meta_dir).mkdir(parents=True, exist_ok=True)
        
        self.db = IndexedRocksDB(meta_dir)
        self.logger = logging.getLogger(__name__)
        
        # 注册模型和索引
        self.db.register_collection(self.__COLLECTION_NAME__, DocumentMeta)
        self.db.register_index(self.__COLLECTION_NAME__, DocumentMeta, "processed")
        self.db.register_index(self.__COLLECTION_NAME__, DocumentMeta, "topic_path")
        
        # 确保基础目录存在
        self.docs_dir = Path(docs_dir)
        self.docs_dir.mkdir(parents=True, exist_ok=True)
    
    # === 文件系统目录管理 ===
    
    def get_user_base(self, user_id: str) -> Path:
        """获取用户根目录"""
        user_dir = self.docs_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir
    
    async def _get_topic_path(self, user_id: str, document_id: str) -> Optional[str]:
        """从元数据获取topic_path"""
        meta = await self.get_metadata(user_id, document_id)
        return meta.get("topic_path") if meta else None
    
    def get_document_path(self, user_id: str, topic_path: str, document_id: str) -> Path:
        """获取文档目录完整路径 - 使用特殊格式标记document_id文件夹"""
        user_base = self.get_user_base(user_id)
        doc_folder = f"__id_{document_id}__"
        
        if topic_path:
            doc_path = user_base / topic_path / doc_folder
        else:
            doc_path = user_base / doc_folder
            
        doc_path.mkdir(parents=True, exist_ok=True)
        return doc_path
    
    # === 元数据管理API ===
    
    async def create_document(
        self,
        user_id: str,
        document_id: str,
        topic_path: str = None,
        initial_meta: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """创建文档元数据和目录结构"""
        # 创建文档目录
        doc_path = self.get_document_path(user_id, topic_path, document_id)
        
        # 准备基础元数据
        now = time.time()
        metadata = {
            "document_id": document_id,
            "user_id": user_id,
            "topic_path": topic_path,
            "created_at": now,
            "updated_at": now,
            "processed": False  # 初始状态为未处理
        }
        
        # 合并传入的元数据
        if initial_meta:
            for k, v in initial_meta.items():
                if k not in ["document_id", "user_id", "created_at", "updated_at"]:
                    metadata[k] = v
                
        # 创建Pydantic模型并保存
        doc_meta = DocumentMeta(**metadata)
        db_key = DocumentMeta.get_db_key(user_id, document_id)
        self.db.update_with_indexes(self.__COLLECTION_NAME__, db_key, doc_meta)
        
        return doc_meta.model_dump()
    
    async def get_metadata(self, user_id: str, document_id: str) -> Optional[Dict[str, Any]]:
        """获取文档元数据 - 直接通过user_id和document_id获取"""
        db_key = DocumentMeta.get_db_key(user_id, document_id)
        return self.db.get(db_key)
    
    async def update_metadata(
        self,
        user_id: str,
        document_id: str,
        update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """更新文档元数据 - 直接通过user_id和document_id定位"""
        db_key = DocumentMeta.get_db_key(user_id, document_id)
        meta = self.db.get(db_key)
        
        if not meta:
            return None
            
        # 更新时间戳
        update_data["updated_at"] = time.time()
        
        # 深度合并
        def deep_update(d, u):
            for k, v in u.items():
                if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                    deep_update(d[k], v)
                else:
                    d[k] = v
        
        updated_dict = meta.copy()
        deep_update(updated_dict, update_data)
        
        # 创建新模型并保存
        updated_meta = DocumentMeta(**updated_dict)
        self.db.update_with_indexes(self.__COLLECTION_NAME__, db_key, updated_meta)
        
        return updated_meta.model_dump()
    
    async def delete_document(self, user_id: str, document_id: str) -> bool:
        """完全删除文档元数据和文件系统资源"""
        # 首先获取元数据，以便知道文件位置
        meta = await self.get_metadata(user_id, document_id)
        if not meta:
            return True  # 文档不存在视为删除成功
        
        # 获取文档路径用于删除文件
        topic_path = meta.get("topic_path")
        doc_path = self.get_document_path(user_id, topic_path, document_id)
        
        # 删除文件系统资源
        if doc_path.exists():
            try:
                import shutil
                shutil.rmtree(doc_path)
                self.logger.info(f"已删除文档文件: {doc_path}")
            except Exception as e:
                self.logger.error(f"删除文档文件失败: {e}")
                return False
        
        # 从RocksDB中删除元数据
        db_key = DocumentMeta.get_db_key(user_id, document_id)
        self.db.delete(db_key)
        self.logger.info(f"已删除文档元数据: {db_key}")
        
        return True
    
    async def list_documents(self, user_id: str, topic_path: str = None) -> List[Dict[str, Any]]:
        """列出指定用户的文档 - 使用前缀查询"""
        prefix = DocumentMeta.get_prefix(user_id)
        docs = self.db.values(prefix=prefix)
        
        # 仅过滤主题
        results = []
        for doc in docs:
            if topic_path is None or doc.get('topic_path') == topic_path:
                results.append(doc)
        
        # 按创建时间排序
        results.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return results
    
    async def find_processed_documents(self, user_id: str, processed: bool = True) -> List[Dict[str, Any]]:
        """查找已处理或未处理的文档"""
        # 使用processed索引查询
        all_docs = self.db.values_with_index(self.__COLLECTION_NAME__, "processed", processed)
        
        # 过滤用户ID
        return [doc.model_dump() for doc in all_docs if doc.user_id == user_id]
    
    # === 文件夹识别辅助函数 ===
    
    def is_document_folder(self, folder_name: str) -> bool:
        """检查文件夹名是否符合document_id格式"""
        return folder_name.startswith("__id_") and folder_name.endswith("__")
    
    def extract_document_id(self, folder_name: str) -> str:
        """从文件夹名提取document_id"""
        if self.is_document_folder(folder_name):
            return folder_name[5:-2]  # 去掉 '__id_' 和 '__'
        return None
    
    def get_document_folder_name(self, document_id: str) -> str:
        """构造document_id文件夹名"""
        return f"__id_{document_id}__"
