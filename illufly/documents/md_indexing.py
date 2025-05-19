import os
import json
from pathlib import Path
from typing import Dict, Any, List, Set, Optional
import asyncio
import logging
from datetime import datetime
from .path_manager import PathManager

class MarkdownIndexing:
    """文档索引管理器 - 维护document_id到路径和元数据的缓存映射"""
    
    def __init__(self, path_manager: PathManager):
        self.path_manager = path_manager
        self.logger = logging.getLogger(__name__)
        self.index: Dict[str, Dict[str, Any]] = {}  # {user_id: {document_id: {path, metadata}}}
        self.user_locks = {}  # 用户级别的锁字典 {user_id: asyncio.Lock()}
        self.last_refresh = {}  # {user_id: timestamp}
        self.refresh_interval = 300  # 秒
        
    def get_user_lock(self, user_id: str) -> asyncio.Lock:
        """获取指定用户的锁，如果不存在则创建"""
        if user_id not in self.user_locks:
            self.user_locks[user_id] = asyncio.Lock()
        return self.user_locks[user_id]
        
    async def refresh_index(self, user_id: str, force: bool = False, specific_path: str = None) -> None:
        """刷新指定用户的文档索引，可选择只刷新特定路径
        
        Args:
            user_id: 用户ID
            force: 是否强制刷新，忽略时间间隔
            specific_path: 如果提供，只刷新该路径下的索引
        """
        now = datetime.now().timestamp()
        if not force and user_id in self.last_refresh:
            if now - self.last_refresh[user_id] < self.refresh_interval:
                return  # 在刷新间隔内，不重复刷新
        
        async with self.get_user_lock(user_id):
            # 初始化用户索引
            if user_id not in self.index:
                self.index[user_id] = {}
                
            # 如果指定了路径，只刷新该路径下的文档
            if specific_path:
                await self._refresh_specific_path(user_id, specific_path, now)
            else:
                # 全量刷新
                await self._refresh_full_index(user_id, now)
            
            # 更新刷新时间
            self.last_refresh[user_id] = now
    
    async def _refresh_specific_path(self, user_id: str, relative_path: str, timestamp: float) -> None:
        """只刷新特定路径下的文档索引"""
        # 处理指定路径的文档
        specific_dir = self.path_manager.get_topic_path(user_id, relative_path)
        
        # 记录该路径下找到的文档ID
        found_docs = set()
        
        if specific_dir.exists():
            # 遍历指定路径及其子目录
            for root, _, files in os.walk(specific_dir):
                for file in files:
                    if file.startswith("__id_") and file.endswith("__.md"):
                        doc_id = self.path_manager.extract_document_id(file)
                        if doc_id:
                            sub_path = Path(root).relative_to(self.path_manager.get_user_base(user_id))
                            topic_path = str(sub_path)
                            
                            # 更新索引
                            self.index[user_id][doc_id] = {
                                "topic_path": topic_path,
                                "file_name": file,
                                "last_checked": timestamp
                            }
                            found_docs.add(doc_id)
            
            # 清理该路径下不存在的文档（需要小心处理，只删除相关文档）
            to_remove = []
            for doc_id, info in self.index.get(user_id, {}).items():
                if info.get("topic_path", "").startswith(relative_path):
                    if doc_id not in found_docs:
                        to_remove.append(doc_id)
            
            for doc_id in to_remove:
                del self.index[user_id][doc_id]
    
    async def _refresh_full_index(self, user_id: str, timestamp: float) -> None:
        """全量刷新用户的文档索引"""
        # 记录所有找到的文档ID
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
                            "last_checked": timestamp
                        }
                        found_docs.add(doc_id)
        
        # 清理索引中不存在的文档
        to_remove = []
        for doc_id in self.index[user_id]:
            if doc_id not in found_docs:
                to_remove.append(doc_id)
        
        for doc_id in to_remove:
            del self.index[user_id][doc_id]
    
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
        # 这里采用更精确的搜索策略，避免全文件系统扫描
        document_found = False
        user_base = self.path_manager.get_user_base(user_id)
        
        # 尝试直接使用文件名搜索（更高效）
        file_name = self.path_manager.get_document_file_name(document_id)
        for root, _, files in os.walk(user_base):
            if file_name in files:
                relative_path = Path(root).relative_to(user_base)
                topic_path = str(relative_path)
                
                # 直接更新索引
                async with self.get_user_lock(user_id):
                    self.index[user_id][document_id] = {
                        "topic_path": topic_path,
                        "file_name": file_name,
                        "last_checked": datetime.now().timestamp()
                    }
                return topic_path
                
        return None
    
    async def add_document(self, user_id: str, document_id: str, topic_path: str, file_name: str) -> None:
        """添加或更新文档索引项
        
        Args:
            user_id: 用户ID
            document_id: 文档ID
            topic_path: 主题路径
            file_name: 文件名
        """
        async with self.get_user_lock(user_id):
            if user_id not in self.index:
                self.index[user_id] = {}
                
            self.index[user_id][document_id] = {
                "topic_path": topic_path,
                "file_name": file_name,
                "last_checked": datetime.now().timestamp()
            }
    
    async def update_document_path(self, user_id: str, document_id: str, new_path: str) -> None:
        """更新文档的路径信息
        
        Args:
            user_id: 用户ID
            document_id: 文档ID
            new_path: 新的主题路径
        """
        async with self.get_user_lock(user_id):
            if user_id in self.index and document_id in self.index[user_id]:
                self.index[user_id][document_id]["topic_path"] = new_path
                self.index[user_id][document_id]["last_checked"] = datetime.now().timestamp()

    async def update_documents_in_path(self, user_id: str, old_path: str, new_path: str) -> None:
        """批量更新指定路径下所有文档的路径
        
        Args:
            user_id: 用户ID
            old_path: 原路径前缀
            new_path: 新路径前缀
        """
        async with self.get_user_lock(user_id):
            if user_id not in self.index:
                return
                
            for doc_id, info in self.index[user_id].items():
                topic_path = info.get("topic_path", "")
                if topic_path == old_path or topic_path.startswith(f"{old_path}/"):
                    # 替换路径前缀
                    if topic_path == old_path:
                        new_topic_path = new_path
                    else:
                        suffix = topic_path[len(old_path)+1:]  # +1 for the slash
                        new_topic_path = f"{new_path}/{suffix}"
                    
                    info["topic_path"] = new_topic_path
                    info["last_checked"] = datetime.now().timestamp()

    async def remove_document(self, user_id: str, document_id: str) -> None:
        """从索引中移除文档
        
        Args:
            user_id: 用户ID
            document_id: 文档ID
        """
        async with self.get_user_lock(user_id):
            if user_id in self.index and document_id in self.index[user_id]:
                del self.index[user_id][document_id]

    async def remove_documents_in_path(self, user_id: str, path: str, recursive: bool = True) -> List[str]:
        """移除指定路径下的所有文档索引
        
        Args:
            user_id: 用户ID
            path: 路径前缀
            recursive: 是否递归删除子路径下的文档
            
        Returns:
            移除的文档ID列表
        """
        removed_docs = []
        
        async with self.get_user_lock(user_id):
            if user_id not in self.index:
                return removed_docs
                
            to_remove = []
            for doc_id, info in self.index[user_id].items():
                topic_path = info.get("topic_path", "")
                
                if topic_path == path or (recursive and topic_path.startswith(f"{path}/")):
                    to_remove.append(doc_id)
            
            for doc_id in to_remove:
                del self.index[user_id][doc_id]
                removed_docs.append(doc_id)
                
        return removed_docs

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
        
    async def save_cache(self, cache_file: str = None) -> bool:
        """保存索引缓存到文件"""
        base_dir = self.path_manager.base_dir
        if not cache_file:
            cache_file = str(base_dir / "index_cache.json")
            
        try:
            cache_data = {
                "timestamp": datetime.now().isoformat(),
                "index": self.index
            }
            
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f)
                
            return True
        except Exception as e:
            self.logger.error(f"保存索引缓存失败: {e}")
            return False
    
    async def load_cache(self, cache_file: str = None) -> bool:
        """从文件加载索引缓存"""
        base_dir = self.path_manager.base_dir
        if not cache_file:
            cache_file = str(base_dir / "index_cache.json")
            
        if not os.path.exists(cache_file):
            return False
            
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                
            # 加载索引，确保结构正确
            self.index = {}
            loaded_index = cache_data["index"]
            
            # 确保结构一致性
            for user_id, docs in loaded_index.items():
                self.index[user_id] = {}
                for doc_id, info in docs.items():
                    # 确保info中的topic_path是字符串，而不是字典
                    if isinstance(info, dict):
                        topic_path = info.get("topic_path", "")
                        if isinstance(topic_path, str):
                            self.index[user_id][doc_id] = info
                        else:
                            # 如果是错误的结构，尝试修复
                            corrected_info = {
                                "topic_path": ".",  # 默认为根目录
                                "file_name": info.get("file_name", f"__id_{doc_id}__.md"),
                                "last_checked": info.get("last_checked", datetime.now().timestamp())
                            }
                            self.index[user_id][doc_id] = corrected_info
                    else:
                        # 如果整个info不是字典，创建一个默认结构
                        self.index[user_id][doc_id] = {
                            "topic_path": ".",
                            "file_name": f"__id_{doc_id}__.md",
                            "last_checked": datetime.now().timestamp()
                        }
                
            self.logger.info(f"成功从缓存加载索引，时间戳: {cache_data['timestamp']}")
            return True
        except Exception as e:
            self.logger.error(f"加载索引缓存失败: {e}")
            return False

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
