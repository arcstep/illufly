import os
from pathlib import Path
from typing import Dict, Any, List, Set, Optional
import asyncio
import logging
from datetime import datetime

class MarkdownIndexing:
    """文档索引管理器 - 维护document_id到路径和元数据的缓存映射"""
    
    def __init__(self, path_manager):
        self.path_manager = path_manager
        self.logger = logging.getLogger(__name__)
        self.index: Dict[str, Dict[str, Any]] = {}  # {user_id: {document_id: {path, metadata}}}
        self.index_lock = asyncio.Lock()
        self.last_refresh = {}  # {user_id: timestamp}
        self.refresh_interval = 300  # 秒
        
    async def refresh_index(self, user_id: str, force: bool = False) -> None:
        """刷新指定用户的文档索引
        
        Args:
            user_id: 用户ID
            force: 是否强制刷新，忽略时间间隔
        """
        now = datetime.now().timestamp()
        if not force and user_id in self.last_refresh:
            if now - self.last_refresh[user_id] < self.refresh_interval:
                return  # 在刷新间隔内，不重复刷新
        
        async with self.index_lock:
            # 初始化用户索引
            if user_id not in self.index:
                self.index[user_id] = {}
                
            # 记录所有找到的文档ID，用于清理不存在的记录
            found_docs = set()
            
            # 遍历用户目录下的所有文件
            user_base = self.path_manager.get_user_base(user_id)
            for root, _, files in os.walk(user_base):
                for file in files:
                    if file.startswith("__id_") and file.endswith("__.md"):
                        doc_id = self.path_manager.extract_document_id(file)
                        if doc_id:
                            relative_path = Path(root).relative_to(user_base)
                            topic_path = str(relative_path)
                            
                            # 更新索引
                            self.index[user_id][doc_id] = {
                                "topic_path": topic_path,
                                "file_name": file,
                                "last_checked": now
                            }
                            found_docs.add(doc_id)
            
            # 清理索引中不存在的文档
            to_remove = []
            for doc_id in self.index[user_id]:
                if doc_id not in found_docs:
                    to_remove.append(doc_id)
            
            for doc_id in to_remove:
                del self.index[user_id][doc_id]
                
            # 更新刷新时间
            self.last_refresh[user_id] = now
    
    async def get_document_path(self, user_id: str, document_id: str) -> Optional[str]:
        """获取文档的主题路径
        
        Args:
            user_id: 用户ID
            document_id: 文档ID
            
        Returns:
            文档所在的主题路径，找不到则返回None
        """
        # 确保索引已初始化
        if user_id not in self.index:
            await self.refresh_index(user_id)
        
        # 尝试从索引中获取
        if document_id in self.index.get(user_id, {}):
            return self.index[user_id][document_id]["topic_path"]
        
        # 索引中没有，尝试搜索文件系统
        await self.refresh_index(user_id, force=True)
        
        # 再次检查
        if document_id in self.index.get(user_id, {}):
            return self.index[user_id][document_id]["topic_path"]
        
        return None
    
    async def list_all_documents(self, user_id: str) -> List[Dict[str, Any]]:
        """列出用户的所有文档及其路径
        
        Args:
            user_id: 用户ID
            
        Returns:
            文档列表，每个项包含document_id和topic_path
        """
        # 刷新索引
        await self.refresh_index(user_id)
        
        result = []
        for doc_id, info in self.index.get(user_id, {}).items():
            result.append({
                "document_id": doc_id,
                "topic_path": info["topic_path"]
            })
        
        return result
    
    async def update_document_path(self, user_id: str, document_id: str, new_path: str) -> None:
        """更新文档的路径信息
        
        Args:
            user_id: 用户ID
            document_id: 文档ID
            new_path: 新的主题路径
        """
        async with self.index_lock:
            if user_id in self.index and document_id in self.index[user_id]:
                self.index[user_id][document_id]["topic_path"] = new_path
                self.index[user_id][document_id]["last_checked"] = datetime.now().timestamp()

    async def initialize(self, callback=None) -> Dict[str, int]:
        """初始化索引，扫描所有用户的文档结构
        
        Args:
            callback: 可选的回调函数，用于报告进度和结果
                     格式为 callback(user_id, current_count, total_count)
        
        Returns:
            包含每个用户文档数量的字典
        """
        result = {}
        # 获取所有用户目录
        base_dir = self.path_manager.base_dir
        if not base_dir.exists():
            return result
        
        # 识别所有用户目录
        user_dirs = [d for d in base_dir.iterdir() if d.is_dir()]
        total_users = len(user_dirs)
        
        self.logger.info(f"开始索引初始化，发现 {total_users} 个用户目录")
        
        # 扫描每个用户的文档
        for i, user_dir in enumerate(user_dirs):
            user_id = user_dir.name
            try:
                # 强制刷新索引
                await self.refresh_index(user_id, force=True)
                
                # 统计文档数量
                doc_count = len(self.index.get(user_id, {}))
                result[user_id] = doc_count
                
                # 报告进度
                if callback:
                    await callback(user_id, i + 1, total_users)
                    
                self.logger.info(f"用户 {user_id} 索引完成，发现 {doc_count} 个文档")
            except Exception as e:
                self.logger.error(f"用户 {user_id} 索引失败: {e}")
        
        # 记录总体结果
        total_docs = sum(result.values())
        self.logger.info(f"索引初始化完成，共 {total_users} 个用户，{total_docs} 个文档")
        
        return result

    async def get_stats(self) -> Dict[str, Any]:
        """获取索引统计信息
        
        Returns:
            包含索引统计信息的字典
        """
        stats = {
            "users": len(self.index),
            "documents": 0,
            "last_refresh": self.last_refresh.copy(),
            "user_stats": {}
        }
        
        for user_id, docs in self.index.items():
            user_doc_count = len(docs)
            stats["documents"] += user_doc_count
            stats["user_stats"][user_id] = {
                "document_count": user_doc_count
            }
        
        return stats
