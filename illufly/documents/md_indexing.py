import os
import json
import asyncio
import logging
import frontmatter as python_frontmatter

from pathlib import Path
from typing import Dict, Any, List, Set, Optional, Tuple
from datetime import datetime
from .path_manager import PathManager

class MarkdownIndexing:
    """文档索引管理器 - 协调文件系统操作和索引更新"""
    
    def __init__(self, path_manager: PathManager):
        self.path_manager = path_manager
        self.logger = logging.getLogger(__name__)
        self.index: Dict[str, Dict[str, Any]] = {}  # {user_id: {document_id: {path, metadata}}}
        self.user_locks = {}  # 用户级别的锁字典 {user_id: asyncio.Lock()}
        self.last_refresh = {}  # {user_id: timestamp}
        self.refresh_interval = 300  # 秒
    
    # ==== 用户锁管理 ====
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
                        doc_id = self.path_manager.extract_document_id(Path(root) / file)
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
                    doc_id = self.path_manager.extract_document_id(Path(root) / file)
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
        """获取文档的主题路径"""
        self.logger.debug(f"获取文档路径: user_id={user_id}, doc_id={document_id}")
        
        # 确保索引已初始化
        if user_id not in self.index:
            self.logger.debug(f"用户索引不存在，初始化: user_id={user_id}")
            await self.refresh_index(user_id, force=True)  # 强制刷新
        
        # 尝试从索引中获取
        if document_id in self.index.get(user_id, {}):
            path = self.index[user_id][document_id]["topic_path"]
            self.logger.debug(f"从索引获取路径: {path}")
            
            # 验证路径对应的文件是否存在
            file_name = self.index[user_id][document_id]["file_name"]
            file_path = self.path_manager.get_topic_path(user_id, path) / file_name
            if not file_path.exists():
                self.logger.warning(f"索引中的文件不存在: {file_path}")
                # 即使文件不存在，也返回索引中的路径
                return path
            
            return path
        
        # 索引中没有，尝试搜索文件系统
        self.logger.debug(f"索引中未找到，搜索文件系统: user_id={user_id}, doc_id={document_id}")
        user_base = self.path_manager.get_user_base(user_id)
        
        # 尝试直接使用文件名搜索
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
                self.logger.debug(f"在文件系统中找到路径: {topic_path}")
                return topic_path
        
        self.logger.error(f"未找到文档路径: user_id={user_id}, doc_id={document_id}")
        return None
    
    async def add_document(self, user_id: str, document_id: str, topic_path: str, file_name: str) -> None:
        """添加或更新文档索引项"""
        self.logger.debug(f"开始更新索引: user_id={user_id}, doc_id={document_id}, topic_path={topic_path}")
        
        async with self.get_user_lock(user_id):
            if user_id not in self.index:
                self.index[user_id] = {}
                self.logger.debug(f"创建用户索引: user_id={user_id}")
            
            # 更新索引
            self.index[user_id][document_id] = {
                "topic_path": topic_path,
                "file_name": file_name,
                "last_checked": datetime.now().timestamp()
            }
            
            # 验证索引更新
            if document_id not in self.index[user_id]:
                self.logger.error(f"索引更新失败: user_id={user_id}, doc_id={document_id}")
            else:
                self.logger.debug(f"索引更新成功: user_id={user_id}, doc_id={document_id}")
    
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
        """初始化索引，扫描所有用户的文档结构"""
        result = {}
        # 获取基本目录（修改这里）
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

    # ==== 文档操作 ====
    async def create_document(self, user_id: str, document_id: str, topic_path: str, 
                             title: str, content: str, metadata: Dict[str, Any]) -> bool:
        """创建新文档并更新索引"""
        self.logger.info(f"开始创建文档: user_id={user_id}, doc_id={document_id}, topic_path={topic_path}")
        
        try:
            # 确保目录存在
            full_topic_path = self.path_manager.get_topic_path(user_id, topic_path)
            self.logger.debug(f"文档完整路径: {full_topic_path}")
            
            if not full_topic_path.exists():
                self.logger.debug(f"创建目录: {full_topic_path}")
                self.path_manager.create_topic_dir(user_id, topic_path)
            
            # 生成文件名和完整路径
            file_name = self.path_manager.get_document_file_name(document_id)
            file_path = full_topic_path / file_name
            self.logger.debug(f"文件路径: {file_path}")
            
            # 准备frontmatter
            post = python_frontmatter.Post(content, **metadata)
            
            # 写入文件
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(python_frontmatter.dumps(post))
            self.logger.debug(f"文件写入成功: {file_path}")
            
            # 更新索引前先验证文件是否存在
            if not file_path.exists():
                self.logger.error(f"文件创建后未找到: {file_path}")
                return False
            
            # 更新索引
            await self.add_document(user_id, document_id, topic_path, file_name)
            self.logger.debug(f"索引更新完成: user_id={user_id}, doc_id={document_id}")
            
            # 验证索引是否更新成功
            doc_path = await self.get_document_path(user_id, document_id)
            if not doc_path:
                self.logger.error(f"索引更新后无法获取文档路径: user_id={user_id}, doc_id={document_id}")
                return False
            
            self.logger.info(f"文档创建成功: user_id={user_id}, doc_id={document_id}, path={doc_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"创建文档失败: {document_id}, 错误: {e}")
            return False
    
    async def delete_document_file(self, user_id: str, document_id: str) -> bool:
        """删除文档文件并更新索引
        
        协调文件系统操作和索引更新，返回是否成功
        """
        # 获取文档路径
        topic_path = await self.get_document_path(user_id, document_id)
        if not topic_path:
            return False
        
        try:
            # 构建文件路径
            file_name = self.path_manager.get_document_file_name(document_id)
            file_path = self.path_manager.get_topic_path(user_id, topic_path) / file_name
            
            # 检查文件是否存在
            if not file_path.exists():
                return False
            
            # 删除文件
            file_path.unlink()
            
            # 更新索引
            await self.remove_document(user_id, document_id)
            
            return True
        except Exception as e:
            self.logger.error(f"删除文档失败: {document_id}, 错误: {e}")
            return False
    
    async def update_document(self, user_id: str, document_id: str, 
                              content: Optional[str] = None, 
                              metadata: Optional[Dict[str, Any]] = None) -> bool:
        """更新文档内容或元数据"""
        self.logger.debug(f"更新文档: user_id={user_id}, doc_id={document_id}")
        
        # 1. 读取当前文档
        document = await self.read_document(user_id, document_id)
        if not document:
            self.logger.error(f"读取文档失败: user_id={user_id}, doc_id={document_id}")
            return False
        
        # 2. 更新内容或元数据
        current_content = document["content"]
        current_metadata = document["metadata"].copy()  # 创建元数据的副本
        
        if content is not None:
            current_content = content
            self.logger.debug(f"更新内容: doc_id={document_id}")
        
        if metadata is not None:
            # 更新元数据，但保留 topic_path
            topic_path = current_metadata.get("topic_path")
            for key, value in metadata.items():
                current_metadata[key] = value
            if topic_path:
                current_metadata["topic_path"] = topic_path
            self.logger.debug(f"更新元数据: doc_id={document_id}, metadata={metadata}")
        
        # 始终更新修改时间
        current_metadata["updated_at"] = datetime.now().isoformat()
        
        # 3. 通过索引管理器更新文档
        try:
            success = await self.update_document_file(
                user_id, 
                document_id, 
                current_content, 
                current_metadata
            )
            
            if not success:
                self.logger.error(f"更新文档文件失败: user_id={user_id}, doc_id={document_id}")
            else:
                self.logger.debug(f"更新文档成功: user_id={user_id}, doc_id={document_id}")
            
            return success
        except Exception as e:
            self.logger.error(f"更新文档时发生异常: user_id={user_id}, doc_id={document_id}, 错误: {e}")
            return False

    async def update_document_file(self, user_id: str, document_id: str, content: str, metadata: Dict[str, Any]) -> bool:
        """更新文档内容和元数据并同步索引"""
        try:
            self.logger.debug(f"开始更新文档文件: user_id={user_id}, doc_id={document_id}")
            
            # 获取当前文档路径
            current_path = await self.get_document_path(user_id, document_id)
            self.logger.debug(f"获取到文档路径: {current_path}")
            if not current_path:
                self.logger.error(f"找不到文档路径: user_id={user_id}, doc_id={document_id}")
                return False
            
            # 构建文件路径
            file_name = self.path_manager.get_document_file_name(document_id)
            file_path = self.path_manager.get_topic_path(user_id, current_path) / file_name
            self.logger.debug(f"构建文件路径: {file_path}")
            
            # 检查文件是否存在
            if not file_path.exists():
                self.logger.error(f"文件不存在: {file_path}")
                return False
            
            # 确保元数据中包含当前路径
            if "topic_path" not in metadata:
                metadata["topic_path"] = current_path
                self.logger.debug(f"添加缺失的 topic_path: {current_path}")
            
            # 写入更新后的内容
            try:
                post = python_frontmatter.Post(content, **metadata)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(python_frontmatter.dumps(post))
                self.logger.debug(f"成功写入文件: {file_path}")
            except Exception as e:
                self.logger.error(f"写入文件失败: {file_path}, 错误: {e}")
                return False
            
            # 如果元数据中的路径与当前路径不同，更新索引
            new_path = metadata.get("topic_path")
            if new_path and new_path != current_path:
                self.logger.debug(f"更新文档路径: {current_path} -> {new_path}")
                await self.update_document_path(user_id, document_id, new_path)
            
            return True
        except Exception as e:
            self.logger.error(f"更新文档失败: {document_id}, 错误: {e}")
            return False
    
    async def move_document_file(self, user_id: str, document_id: str, 
                               target_path: str) -> bool:
        """移动文档到新路径并更新索引
        
        协调文件系统操作和索引更新，返回是否成功
        """
        # 获取当前文档路径
        current_path = await self.get_document_path(user_id, document_id)
        if not current_path:
            return False
        
        try:
            # 构建源文件和目标文件路径
            file_name = self.path_manager.get_document_file_name(document_id)
            source_path = self.path_manager.get_topic_path(user_id, current_path) / file_name
            
            # 确保目标目录存在
            target_dir = self.path_manager.get_topic_path(user_id, target_path)
            if not target_dir.exists():
                self.path_manager.create_topic_dir(user_id, target_path)
            
            target_file = target_dir / file_name
            
            # 检查目标文件是否已存在
            if target_file.exists():
                return False
            
            # 移动文件
            source_path.rename(target_file)
            
            # 更新索引
            await self.update_document_path(user_id, document_id, target_path)
            
            return True
        except Exception as e:
            self.logger.error(f"移动文档失败: {document_id}, 错误: {e}")
            return False
    
    # ==== 主题操作 ====
    async def create_topic(self, user_id: str, relative_path: str) -> bool:
        """创建主题目录，仅封装文件系统操作"""
        return self.path_manager.create_topic_dir(user_id, relative_path)
    
    async def delete_topic(self, user_id: str, relative_path: str) -> bool:
        """删除主题目录并更新索引"""
        # 先找到该主题下的所有文档
        document_ids = self.path_manager.get_physical_document_ids(user_id, relative_path)
        
        # 执行文件系统删除操作
        success = self.path_manager.delete_topic_dir(user_id, relative_path)
        
        if success:
            # 从索引中移除所有相关文档
            await self.remove_documents_in_path(user_id, relative_path)
        
        return success
    
    async def rename_topic(self, user_id: str, old_path: str, new_name: str) -> Tuple[bool, str]:
        """重命名主题目录并更新索引"""
        # 获取受影响的文档ID
        document_ids = self.path_manager.get_physical_document_ids(user_id, old_path)
        
        # 执行文件系统重命名操作
        success, new_path = self.path_manager.rename_topic_dir(user_id, old_path, new_name)
        
        if success:
            # 刷新索引以确保文件系统变更已反映
            await self.refresh_index(user_id, force=True, specific_path=new_path)
            
            # 批量更新索引中的文档路径
            await self.update_documents_in_path(user_id, old_path, new_path)
            
            return True, new_path
        
        return False, ""
    
    async def move_topic(self, user_id: str, source_path: str, target_path: str) -> Tuple[bool, str]:
        """移动主题目录并更新索引"""
        # 执行文件系统移动操作
        success, new_path = self.path_manager.move_topic_dir(user_id, source_path, target_path)
        
        if success:
            # 刷新索引以确保文件系统变更已反映
            await self.refresh_index(user_id, force=True, specific_path=new_path)
            
            # 批量更新索引中的文档路径
            await self.update_documents_in_path(user_id, source_path, new_path)
            
            return True, new_path
        
        return False, ""
    
    async def copy_topic(self, user_id: str, source_path: str, target_path: str) -> Tuple[bool, str]:
        """复制主题目录并更新索引"""
        # 执行文件系统复制操作
        success, new_path = self.path_manager.copy_topic_dir(user_id, source_path, target_path)
        
        if success:
            # 刷新索引以反映新复制的文件
            await self.refresh_index(user_id, force=True, specific_path=new_path)
            return True, new_path
        
        return False, ""
    
    async def merge_topics(self, user_id: str, source_path: str, target_path: str, 
                         overwrite: bool = False) -> bool:
        """合并主题目录并更新索引"""
        # 记录源路径下的所有文档ID
        source_doc_ids = self.path_manager.get_physical_document_ids(user_id, source_path)
        
        # 执行文件系统合并操作
        success = self.path_manager.merge_topic_dirs(user_id, source_path, target_path, overwrite)
        
        if success:
            # 刷新目标目录的索引
            await self.refresh_index(user_id, force=True, specific_path=target_path)
            
            return True
        
        return False
    
    # ==== 文档读取 ====
    async def read_document_file(self, user_id: str, document_id: str) -> Optional[Dict[str, Any]]:
        """读取文档内容和元数据
        
        协调文件系统操作和索引查找
        """
        # 从索引获取路径
        topic_path = await self.get_document_path(user_id, document_id)
        if not topic_path:
            return None
        
        # 构建文件路径
        file_name = self.path_manager.get_document_file_name(document_id)
        file_path = self.path_manager.get_topic_path(user_id, topic_path) / file_name
        
        # 如果文件不在索引路径，尝试在文件系统中搜索
        if not file_path.exists():
            self.logger.debug(f"索引路径下文件不存在，尝试搜索文件系统: {file_path}")
            user_base = self.path_manager.get_user_base(user_id)
            for root, _, files in os.walk(user_base):
                if file_name in files:
                    file_path = Path(root) / file_name
                    # 更新索引中的路径
                    relative_path = Path(root).relative_to(user_base)
                    new_topic_path = str(relative_path)
                    await self.update_document_path(user_id, document_id, new_topic_path)
                    self.logger.info(f"在文件系统中找到文件，更新索引路径: {new_topic_path}")
                    break
            else:
                self.logger.error(f"未找到文档文件: {document_id}")
                return None
        
        try:
            # 读取文件
            with open(file_path, 'r', encoding='utf-8') as f:
                post = python_frontmatter.load(f)
            
            # 构建返回结果
            result = {
                "document_id": document_id,
                "content": post.content,
                "metadata": dict(post.metadata),
                "topic_path": topic_path,
                "file_path": str(file_path)
            }
            return result
        except Exception as e:
            self.logger.error(f"读取文档失败: {document_id}, 错误: {e}")
            return None

    def get_topic_path(self, user_id: str, topic_path: str) -> Path:
        """获取主题的完整路径"""
        return self.path_manager.get_topic_path(user_id, topic_path)

    def get_physical_document_ids(self, user_id: str, topic_path: str) -> List[str]:
        """获取指定主题路径下的所有文档ID"""
        return self.path_manager.get_physical_document_ids(user_id, topic_path)

    def get_document_file_name(self, document_id: str) -> str:
        """获取文档的文件名"""
        return self.path_manager.get_document_file_name(document_id)

    async def get_topic_structure(self, user_id: str, relative_path: str = "") -> Dict[str, Any]:
        """获取主题结构信息"""
        # 确保目录存在
        topic_dir = self.path_manager.get_topic_path(user_id, relative_path)
        
        result = {
            "user_id": user_id,
            "path": relative_path,
            "subtopics": [],
            "document_ids": []
        }
        
        if not topic_dir.exists():
            return result
        
        # 获取子主题
        for item in topic_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                result["subtopics"].append(item.name)
        
        # 获取文档
        for item in topic_dir.iterdir():
            if item.is_file() and item.name.startswith("__id_") and item.name.endswith("__.md"):
                doc_id = self.path_manager.extract_document_id(item)
                if doc_id:
                    result["document_ids"].append(doc_id)
        
        # 排序
        result["subtopics"].sort()
        result["document_ids"].sort()
        
        return result

    # 增强版的移动文档方法，包含元数据更新
    async def move_document(self, user_id: str, document_id: str, target_topic_path: str) -> bool:
        """完整的文档移动操作，包括文件移动、元数据更新和索引更新"""
        try:
            # 1. 获取当前文档信息
            current_doc = await self.read_document_file(user_id, document_id)
            if not current_doc:
                return False
            
            # 2. 检查目标路径是否有效
            if not target_topic_path:
                return False
            
            # 3. 确保目标目录存在
            target_dir = self.path_manager.get_topic_path(user_id, target_topic_path)
            if not target_dir.exists():
                self.path_manager.create_topic_dir(user_id, target_topic_path)
            
            # 4. 移动文件
            file_name = self.path_manager.get_document_file_name(document_id)
            source_path = self.path_manager.get_topic_path(user_id, current_doc["topic_path"]) / file_name
            target_file = target_dir / file_name
            
            # 检查目标文件是否已存在
            if target_file.exists():
                return False
            
            # 执行移动
            source_path.rename(target_file)
            
            # 5. 更新元数据和索引
            metadata = current_doc["metadata"]
            metadata["topic_path"] = target_topic_path
            metadata["updated_at"] = datetime.now().isoformat()
            
            # 更新索引
            await self.update_document_path(user_id, document_id, target_topic_path)
            
            # 保存更新后的文档
            return await self.update_document_file(user_id, document_id, current_doc["content"], metadata)
        except Exception as e:
            self.logger.error(f"移动文档失败: {document_id}, 错误: {e}")
            return False

    # 增强版的主题操作方法，包含元数据批量更新
    async def rename_topic_with_metadata(self, user_id: str, old_path: str, new_name: str) -> bool:
        """重命名主题，同时更新所有文档的元数据"""
        # 1. 获取所有受影响的文档ID
        document_ids = self.path_manager.get_physical_document_ids(user_id, old_path)
        
        # 2. 执行重命名操作
        success, new_path = await self.rename_topic(user_id, old_path, new_name)
        if not success:
            return False
        
        # 3. 更新文档元数据
        for doc_id in document_ids:
            document = await self.read_document_file(user_id, doc_id)
            if document:
                metadata = document["metadata"]
                if metadata.get("topic_path") != new_path:
                    metadata["topic_path"] = new_path
                    metadata["updated_at"] = datetime.now().isoformat()
                    
                    # 更新文件
                    await self.update_document_file(user_id, doc_id, document["content"], metadata)
        
        # 4. 处理子主题下的文档
        await self.verify_and_repair_document_paths(user_id, new_path)
        
        return True

    async def move_topic_with_metadata(self, user_id: str, source_path: str, target_path: str) -> bool:
        """移动主题，同时更新所有文档的元数据"""
        # 1. 获取受影响的文档ID
        document_ids = self.path_manager.get_physical_document_ids(user_id, source_path)
        
        # 2. 执行移动操作
        success, new_path = await self.move_topic(user_id, source_path, target_path)
        if not success:
            return False
        
        # 3. 刷新索引
        await self.refresh_index(user_id, force=True, specific_path=new_path)
        
        # 4. 更新所有文档元数据
        for doc_id in document_ids:
            document = await self.read_document_file(user_id, doc_id)
            if document:
                old_doc_path = document["metadata"].get("topic_path", "")
                # 计算新路径
                if old_doc_path == source_path:
                    new_doc_path = new_path
                else:
                    sub_path = old_doc_path[len(source_path)+1:]  # +1 for slash
                    new_doc_path = f"{new_path}/{sub_path}"
                
                # 更新元数据
                metadata = document["metadata"]
                metadata["topic_path"] = new_doc_path
                metadata["updated_at"] = datetime.now().isoformat()
                
                # 保存更新
                await self.update_document_file(user_id, doc_id, document["content"], metadata)
        
        # 5. 递归处理子主题
        await self.verify_and_repair_document_paths(user_id, new_path)
        
        return True

    async def copy_topic_with_metadata(self, user_id: str, source_path: str, target_path: str) -> bool:
        """复制主题，同时创建所有文档的元数据"""
        # 1. 执行复制操作
        success, new_path = await self.copy_topic(user_id, source_path, target_path)
        if not success:
            return False
        
        # 2. 刷新索引
        await self.refresh_index(user_id, force=True, specific_path=new_path)
        
        # 3. 获取新目录下的文档ID
        new_doc_ids = self.path_manager.get_physical_document_ids(user_id, new_path)
        
        # 4. 更新复制的文档元数据
        for doc_id in new_doc_ids:
            document = await self.read_document_file(user_id, doc_id)
            if document:
                metadata = document["metadata"]
                metadata["topic_path"] = new_path
                metadata["updated_at"] = datetime.now().isoformat()
                
                # 保存更新
                await self.update_document_file(user_id, doc_id, document["content"], metadata)
        
        # 5. 递归处理子主题
        await self.verify_and_repair_document_paths(user_id, new_path)
        
        return True

    async def merge_topics_with_metadata(self, user_id: str, source_path: str, target_path: str, overwrite: bool = False) -> bool:
        """合并主题，同时更新所有文档的元数据"""
        # 1. 获取源路径的文档ID
        source_doc_ids = self.path_manager.get_physical_document_ids(user_id, source_path)
        
        # 2. 执行合并操作
        success = await self.merge_topics(user_id, source_path, target_path, overwrite)
        if not success:
            return False
        
        # 3. 刷新索引
        await self.refresh_index(user_id, force=True, specific_path=target_path)
        
        # 4. 更新文档元数据
        for doc_id in source_doc_ids:
            document = await self.read_document_file(user_id, doc_id)
            if document:
                old_doc_path = document["metadata"].get("topic_path", "")
                # 计算新路径
                if old_doc_path == source_path:
                    new_doc_path = target_path
                else:
                    sub_path = old_doc_path[len(source_path)+1:]  # +1 for slash
                    new_doc_path = f"{target_path}/{sub_path}"
                
                # 更新元数据
                metadata = document["metadata"]
                metadata["topic_path"] = new_doc_path
                metadata["updated_at"] = datetime.now().isoformat()
                
                # 保存更新
                await self.update_document_file(user_id, doc_id, document["content"], metadata)
        
        # 5. 递归处理目标目录
        await self.verify_and_repair_document_paths(user_id, target_path)
        
        return True

    async def verify_and_repair_document_paths(self, user_id: str, topic_path: str = "") -> None:
        """验证主题下所有文档的元数据与文件系统位置一致性，并自动修复"""
        try:
            # 1. 强制刷新索引
            await self.refresh_index(user_id, force=True, specific_path=topic_path)
            
            # 2. 获取文件系统中的文档
            fs_document_ids = self.path_manager.get_physical_document_ids(user_id, topic_path)
            
            # 3. 更新文档元数据
            for doc_id in fs_document_ids:
                try:
                    # 获取文件路径
                    file_name = self.path_manager.get_document_file_name(doc_id)
                    file_path = self.path_manager.get_topic_path(user_id, topic_path) / file_name
                    
                    if not file_path.exists():
                        continue
                    
                    # 读取文档
                    with open(file_path, 'r', encoding='utf-8') as f:
                        post = python_frontmatter.load(f)
                    
                    # 检查并修复元数据
                    metadata = dict(post.metadata)
                    if metadata.get("topic_path") != topic_path:
                        self.logger.info(f"修复文档路径: {doc_id} 从 {metadata.get('topic_path')} 到 {topic_path}")
                        metadata["topic_path"] = topic_path
                        metadata["updated_at"] = datetime.now().isoformat()
                        
                        # 更新文档
                        post.metadata = metadata
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(python_frontmatter.dumps(post))
                            
                        # 更新索引
                        await self.update_document_path(user_id, doc_id, topic_path)
                except Exception as e:
                    self.logger.error(f"修复文档路径失败: {doc_id}, 错误: {e}")
                    continue
                
            # 4. 递归处理子主题
            topic_structure = await self.get_topic_structure(user_id, topic_path)
            for subtopic in topic_structure["subtopics"]:
                subtopic_path = f"{topic_path}/{subtopic}".lstrip("/")
                await self.verify_and_repair_document_paths(user_id, subtopic_path)
        except Exception as e:
            self.logger.error(f"验证和修复文档路径失败: {topic_path}, 错误: {e}")
