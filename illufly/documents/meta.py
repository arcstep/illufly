from pathlib import Path
from typing import Dict, Any, Optional, List
import aiofiles
import json
import logging
import time
from pydantic import BaseModel, Field

from voidring import IndexedRocksDB

class DocumentMeta(BaseModel):
    """文档元数据模型 - 用于RocksDB存储"""
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
    state: str = Field(default="init", description="文档状态")
    sub_state: str = Field(default="none", description="子状态")
    resources: Dict[str, Any] = Field(default_factory=dict, description="资源信息")
    state_details: Dict[str, Any] = Field(default_factory=dict, description="状态详情")
    state_history: List[Dict[str, Any]] = Field(default_factory=list, description="状态历史")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="用户自定义元数据")
    collection_name: Optional[str] = Field(default=None, description="向量集合名称")

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
    """增强版文档元数据管理器 - 使用RocksDB高效管理元数据，文件系统管理实际文件
    
    关键概念:
    1. 文档(Document) - 由document_id唯一标识的内容实体，可以是本地上传文件、网页书签或对话记录
    
    2. 状态(State) - 文档在处理流程中的阶段:
       - init: 初始状态
       - uploaded/bookmarked/saved_chat: 来源状态
       - markdowned: 已转换为Markdown格式
       - chunked: 已切分为内容块
       - qa_extracted: 已提取问答对
       - embedded: 已生成向量嵌入
    
    3. 子状态(SubState) - 当前状态的处理进度:
       - none: 无特定子状态
       - processing: 处理中
       - completed: 处理完成
       - failed: 处理失败
    
    4. 资源(Resource) - 文档处理过程中生成的实际数据:
       - markdown: Markdown格式内容
       - chunks: 文本切片数据
       - qa_pairs: 问答对数据
       - embeddings: 向量嵌入数据
    
    状态和资源的关系:
    - 当文档进入某状态(如markdowned)时，通常表示已生成对应资源(如markdown资源)
    - 资源存储在文件系统中，资源元数据记录在document.resources字典中
    - 状态变更历史记录在document.state_history列表中
    
    典型文档处理流程:
    1. 文档上传/保存 -> init -> uploaded/bookmarked/saved_chat状态
    2. 处理转换 -> processing子状态 -> completed/failed子状态
    3. 状态前进或回退，资源生成或清理
    """
    
    __COLLECTION_NAME__ = "document_meta"
    
    def __init__(self, meta_dir: str, docs_dir: str):
        # 确保meta_dir目录存在
        Path(meta_dir).mkdir(parents=True, exist_ok=True)
        
        self.db = IndexedRocksDB(meta_dir)
        self.logger = logging.getLogger(__name__)
        
        # 注册模型和索引
        self.db.register_collection(self.__COLLECTION_NAME__, DocumentMeta)
        self.db.register_index(self.__COLLECTION_NAME__, DocumentMeta, "state")
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
            "state": "init"
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
    
    async def find_documents_by_state(self, user_id: str, state: str) -> List[Dict[str, Any]]:
        """查找特定状态的文档"""
        # 先获取所有指定状态的文档
        state_docs = self.db.values_with_index(self.__COLLECTION_NAME__, "state", state)
        
        # 过滤用户ID
        return [doc.model_dump() for doc in state_docs if doc.user_id == user_id]
    
    # === 状态管理钩子 ===
    
    async def change_state(
        self,
        user_id: str,
        document_id: str,
        new_state: str,
        details: Dict[str, Any] = None,
        sub_state: str = "none"
    ) -> bool:
        """更改文档状态"""
        meta = await self.get_metadata(user_id, document_id)
        if not meta:
            return False
            
        # 构建更新数据
        update_data = {
            "state": new_state,  # 更新当前状态
            "sub_state": sub_state
        }
        
        if details:
            update_data["state_details"] = details
            
        # 确保状态有变化时才添加历史
        if meta.get("state") != new_state or meta.get("sub_state") != sub_state:
            history_entry = {
                "timestamp": time.time(),
                "state": new_state,
                "sub_state": sub_state
            }
            
            if details:
                history_entry["details"] = details
            
            state_history = meta.get("state_history", [])
            state_history.append(history_entry)
            update_data["state_history"] = state_history
        
        result = await self.update_metadata(user_id, document_id, update_data)
        return result is not None
    
    async def add_resource(
        self,
        user_id: str,
        document_id: str,
        resource_type: str,
        resource_info: Dict[str, Any]
    ) -> bool:
        """添加资源信息到元数据"""
        meta = await self.get_metadata(user_id, document_id)
        if not meta:
            return False
            
        # 获取现有资源
        resources = meta.get("resources", {})
        resources[resource_type] = resource_info
        
        # 更新元数据
        update_data = {
            "resources": resources
        }
        
        result = await self.update_metadata(user_id, document_id, update_data)
        return result is not None
    
    async def remove_resource(
        self,
        user_id: str,
        document_id: str,
        resource_type: str
    ) -> bool:
        """从元数据中彻底移除指定资源信息"""
        meta = await self.get_metadata(user_id, document_id)
        if not meta:
            return False

        resources = meta.get("resources", {})
        if resource_type not in resources:
            self.logger.warning(f"尝试删除不存在的资源: {resource_type}, 文档: {document_id}")
            return True  # 资源本就不存在

        # 构造新的元数据字典，完全替换 resources
        updated_dict = meta.copy()
        updated_dict["resources"] = {k: v for k, v in resources.items() if k != resource_type}
        updated_dict["updated_at"] = time.time()

        # 保存到 RocksDB
        db_key = DocumentMeta.get_db_key(user_id, document_id)
        updated_meta = DocumentMeta(**updated_dict)
        self.db.update_with_indexes(self.__COLLECTION_NAME__, db_key, updated_meta)

        self.logger.info(f"成功移除资源 {resource_type} 从文档 {document_id}")
        return True
    
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
