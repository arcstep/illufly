from pathlib import Path
from typing import Dict, Any, Optional
import aiofiles
import json
import logging
import time

class DocumentMetaManager:
    """文档元数据管理器 - 支持多用户隔离"""
    
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
    
    def get_user_base(self, user_id: str) -> Path:
        """获取用户根目录"""
        user_dir = self.base_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir
    
    def get_document_path(self, user_id: str, topic_path: str, document_id: str) -> Path:
        """获取文档目录完整路径"""
        user_base = self.get_user_base(user_id)
        if topic_path:
            return user_base / topic_path / document_id
        return user_base / document_id
    
    def get_meta_path(self, user_id: str, topic_path: str, document_id: str) -> Path:
        """获取元数据文件路径"""
        return self.get_document_path(user_id, topic_path, document_id) / "meta.json"
    
    async def create_document(
        self,
        user_id: str,
        topic_path: str,
        document_id: str,
        initial_meta: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """创建文档目录和初始元数据
        
        Args:
            user_id: 用户ID
            topic_path: 主题路径
            document_id: 文档ID
            initial_meta: 初始元数据
            
        Returns:
            Dict: 创建的元数据
        """
        doc_path = self.get_document_path(user_id, topic_path, document_id)
        meta_path = self.get_meta_path(user_id, topic_path, document_id)
        
        # 确保目录存在
        doc_path.mkdir(parents=True, exist_ok=True)
        
        # 准备基础元数据
        now = time.time()
        metadata = {
            "user_id": user_id,
            "document_id": document_id,
            "topic_path": topic_path,
            "created_at": now,
            "updated_at": now,
            "state": "created"  # 初始状态
        }
        
        # 合并传入的元数据
        if initial_meta:
            metadata.update(initial_meta)
            
        # 保存元数据
        async with aiofiles.open(meta_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(metadata, ensure_ascii=False, indent=2))
            
        return metadata
    
    async def get_metadata(self, user_id: str, topic_path: str, document_id: str) -> Optional[Dict[str, Any]]:
        """获取文档元数据
        
        Args:
            user_id: 用户ID
            topic_path: 主题路径
            document_id: 文档ID
            
        Returns:
            Dict|None: 元数据或None(不存在时)
        """
        meta_path = self.get_meta_path(user_id, topic_path, document_id)
        
        if not meta_path.exists():
            return None
            
        try:
            async with aiofiles.open(meta_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            logging.error(f"读取元数据失败: {user_id}/{topic_path}/{document_id}, 错误: {e}")
            return None
    
    async def update_metadata(
        self,
        user_id: str,
        topic_path: str,
        document_id: str,
        update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """更新文档元数据
        
        Args:
            user_id: 用户ID
            topic_path: 主题路径
            document_id: 文档ID
            update_data: 要更新的元数据字段
            
        Returns:
            Dict|None: 更新后的完整元数据或None(失败时)
        """
        # 获取当前元数据
        current_meta = await self.get_metadata(user_id, topic_path, document_id)
        if not current_meta:
            return None
            
        # 深度合并更新
        def deep_update(d, u):
            for k, v in u.items():
                if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                    deep_update(d[k], v)
                else:
                    d[k] = v
        
        # 更新元数据
        deep_update(current_meta, update_data)
        current_meta["updated_at"] = time.time()
        
        # 保存更新后的元数据
        meta_path = self.get_meta_path(user_id, topic_path, document_id)
        try:
            async with aiofiles.open(meta_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(current_meta, ensure_ascii=False, indent=2))
            return current_meta
        except Exception as e:
            logging.error(f"更新元数据失败: {user_id}/{topic_path}/{document_id}, 错误: {e}")
            return None
    
    async def delete_document(self, user_id: str, topic_path: str, document_id: str) -> bool:
        """删除文档目录及其所有内容
        
        Args:
            user_id: 用户ID
            topic_path: 主题路径
            document_id: 文档ID
            
        Returns:
            bool: 删除是否成功
        """
        doc_path = self.get_document_path(user_id, topic_path, document_id)
        
        if not doc_path.exists():
            return True  # 不存在视为成功
            
        try:
            import shutil
            shutil.rmtree(doc_path)
            return True
        except Exception as e:
            logging.error(f"删除文档失败: {user_id}/{topic_path}/{document_id}, 错误: {e}")
            return False
    
    async def copy_document(
        self,
        user_id: str,
        src_topic: str,
        src_doc_id: str,
        dst_topic: str,
        dst_doc_id: str = None
    ) -> Optional[Dict[str, Any]]:
        """复制文档到新位置
        
        Args:
            user_id: 用户ID
            src_topic: 源主题路径
            src_doc_id: 源文档ID
            dst_topic: 目标主题路径
            dst_doc_id: 目标文档ID(不提供则使用原ID)
            
        Returns:
            Dict|None: 新文档的元数据或None(失败时)
        """
        src_path = self.get_document_path(user_id, src_topic, src_doc_id)
        dst_doc_id = dst_doc_id or src_doc_id
        dst_path = self.get_document_path(user_id, dst_topic, dst_doc_id)
        
        if not src_path.exists():
            return None
            
        if dst_path.exists():
            return None  # 目标已存在
            
        try:
            # 创建目标目录
            dst_path.mkdir(parents=True, exist_ok=True)
            
            # 复制所有内容(元数据除外)
            import shutil
            for item in src_path.iterdir():
                if item.name != "meta.json":
                    if item.is_dir():
                        shutil.copytree(item, dst_path / item.name)
                    else:
                        shutil.copy2(item, dst_path / item.name)
            
            # 获取并更新元数据
            meta = await self.get_metadata(user_id, src_topic, src_doc_id)
            if meta:
                meta["user_id"] = user_id
                meta["document_id"] = dst_doc_id
                meta["topic_path"] = dst_topic
                meta["copied_from"] = {"topic": src_topic, "document_id": src_doc_id}
                meta["updated_at"] = time.time()
                
                # 保存新元数据
                dst_meta_path = dst_path / "meta.json"
                async with aiofiles.open(dst_meta_path, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(meta, ensure_ascii=False, indent=2))
                    
                return meta
            
            return None
        except Exception as e:
            logging.error(f"复制文档失败: {user_id}/{src_topic}/{src_doc_id} -> {user_id}/{dst_topic}/{dst_doc_id}, 错误: {e}")
            
            # 清理可能部分创建的目标
            if dst_path.exists():
                try:
                    shutil.rmtree(dst_path)
                except:
                    pass
                    
            return None
    
    async def move_document(
        self,
        user_id: str,
        src_topic: str,
        src_doc_id: str,
        dst_topic: str,
        dst_doc_id: str = None
    ) -> Optional[Dict[str, Any]]:
        """移动文档到新位置
        
        Args:
            user_id: 用户ID
            src_topic: 源主题路径
            src_doc_id: 源文档ID
            dst_topic: 目标主题路径
            dst_doc_id: 目标文档ID(不提供则使用原ID)
            
        Returns:
            Dict|None: 移动后的元数据或None(失败时)
        """
        # 先复制文档
        result = await self.copy_document(user_id, src_topic, src_doc_id, dst_topic, dst_doc_id)
        if result:
            # 复制成功后删除源文档
            success = await self.delete_document(user_id, src_topic, src_doc_id)
            if success:
                # 更新元数据，标记为移动而非复制
                dst_doc_id = dst_doc_id or src_doc_id
                result = await self.update_metadata(user_id, dst_topic, dst_doc_id, {
                    "moved_from": {"topic": src_topic, "document_id": src_doc_id},
                    "copied_from": None  # 移除复制标记
                })
                
            return result
        return None
    
    async def document_exists(self, user_id: str, topic_path: str, document_id: str) -> bool:
        """检查文档是否存在
        
        Args:
            user_id: 用户ID
            topic_path: 主题路径
            document_id: 文档ID
            
        Returns:
            bool: 文档是否存在
        """
        meta_path = self.get_meta_path(user_id, topic_path, document_id)
        return meta_path.exists()
    
    # === 状态机钩子方法 ===
    
    async def change_state(
        self,
        user_id: str,
        topic_path: str,
        document_id: str,
        new_state: str,
        details: Dict[str, Any] = None,
        sub_state: str = "none"
    ) -> bool:
        """更改文档状态 - 支持子状态"""
        update_data = {
            "state": new_state,
            "sub_state": sub_state
        }
        
        if details:
            # 添加状态变更详情
            update_data["state_details"] = details
            update_data["state_history"] = {"timestamp": time.time(), "state": new_state, "sub_state": sub_state, "details": details}
        
        result = await self.update_metadata(user_id, topic_path, document_id, update_data)
        return result is not None
    
    async def add_resource(
        self,
        user_id: str,
        topic_path: str,
        document_id: str,
        resource_type: str,
        resource_info: Dict[str, Any]
    ) -> bool:
        """添加资源信息到元数据 - 状态机钩子
        
        Args:
            user_id: 用户ID
            topic_path: 主题路径
            document_id: 文档ID
            resource_type: 资源类型(如'markdown', 'chunks'等)
            resource_info: 资源信息
            
        Returns:
            bool: 添加是否成功
        """
        update_data = {
            "user_id": user_id,
            "resources": {
                resource_type: resource_info
            },
            f"has_{resource_type}": True
        }
        
        result = await self.update_metadata(user_id, topic_path, document_id, update_data)
        return result is not None
    
    async def remove_resource(
        self,
        user_id: str,
        topic_path: str,
        document_id: str,
        resource_type: str
    ) -> bool:
        """从元数据中移除资源信息 - 状态机钩子
        
        Args:
            user_id: 用户ID
            topic_path: 主题路径
            document_id: 文档ID
            resource_type: 资源类型(如'markdown', 'chunks'等)
            
        Returns:
            bool: 移除是否成功
        """
        # 获取当前元数据
        meta = await self.get_metadata(user_id, topic_path, document_id)
        if not meta:
            return False
            
        # 移除资源信息
        if "resources" in meta and resource_type in meta["resources"]:
            del meta["resources"][resource_type]
            
        # 更新标志
        meta[f"has_{resource_type}"] = False
        
        # 更新元数据
        result = await self.update_metadata(user_id, topic_path, document_id, meta)
        return result is not None
