import os
import re
import uuid
import logging
import frontmatter
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from .path_manager import PathManager
from .indexing import DocumentIndexManager

class MarkdownManager:
    """Markdown文档管理器 - 处理文档内容、元数据、主题结构和索引"""
    
    def __init__(self, base_dir: str):
        """初始化Markdown管理器"""
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        
        # 创建辅助管理器
        self.path_manager = PathManager(base_dir)
        self.index_manager = DocumentIndexManager(self.path_manager)
        
        # 内部维护文档索引
        self.document_index = {}  # {user_id: {document_id: {topic_path, file_name, last_checked}}}
        self.index_lock = asyncio.Lock()
        self.last_refresh = {}  # {user_id: timestamp}
        self.refresh_interval = 300  # 秒
    
    def get_user_base(self, user_id: str) -> Path:
        """获取用户根目录"""
        user_dir = self.base_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir
    
    def get_topic_path(self, user_id: str, relative_path: str = "") -> Path:
        """获取用户下的主题路径"""
        user_base = self.get_user_base(user_id)
        if relative_path:
            return user_base / relative_path
        return user_base
    
    def is_document_file(self, file_path: Path) -> bool:
        """判断文件是否为文档文件（使用__id_{document_id}__.md命名规则）"""
        return (file_path.name.startswith("__id_") and 
                file_path.name.endswith("__.md") and 
                file_path.is_file())
    
    def extract_document_id(self, file_path: Path) -> str:
        """从文档文件路径提取document_id"""
        name = file_path.name if isinstance(file_path, Path) else file_path
        if isinstance(name, Path):
            name = name.name
            
        # 处理 __id_xxxx__.md 格式
        if name.startswith("__id_") and name.endswith("__.md"):
            return name[5:-5]  # 去掉 '__id_' 和 '__.md'
        return None

    def get_document_file_name(self, document_id: str) -> str:
        """根据document_id构造标准文件名"""
        return f"__id_{document_id}__.md"
    
    async def initialize(self, callback=None):
        """初始化系统，构建文档索引"""
        # 获取所有用户目录
        if not self.base_dir.exists():
            return {}
            
        result = {}
        user_dirs = [d for d in self.base_dir.iterdir() if d.is_dir()]
        
        self.logger.info(f"开始初始化，发现 {len(user_dirs)} 个用户目录")
        
        for i, user_dir in enumerate(user_dirs):
            user_id = user_dir.name
            try:
                # 刷新用户索引
                await self._refresh_user_index(user_id, force=True)
                
                # 统计文档数量
                doc_count = len(self.document_index.get(user_id, {}))
                result[user_id] = doc_count
                
                # 报告进度
                if callback:
                    await callback(user_id, i + 1, len(user_dirs))
                    
                self.logger.info(f"用户 {user_id} 索引完成，发现 {doc_count} 个文档")
            except Exception as e:
                self.logger.error(f"用户 {user_id} 索引失败: {e}")
        
        # 记录总体结果
        total_docs = sum(result.values())
        self.logger.info(f"初始化完成，共 {len(user_dirs)} 个用户，{total_docs} 个文档")
        
        return result
    
    async def _refresh_user_index(self, user_id: str, force: bool = False) -> None:
        """刷新指定用户的文档索引"""
        now = datetime.now().timestamp()
        if not force and user_id in self.last_refresh:
            if now - self.last_refresh[user_id] < self.refresh_interval:
                return  # 在刷新间隔内，不重复刷新
        
        async with self.index_lock:
            # 初始化用户索引
            if user_id not in self.document_index:
                self.document_index[user_id] = {}
                
            # 记录所有找到的文档ID
            found_docs = set()
            
            # 遍历用户目录下的所有文件
            user_base = self.get_user_base(user_id)
            for root, _, files in os.walk(user_base):
                for file in files:
                    if file.startswith("__id_") and file.endswith("__.md"):
                        doc_id = self.extract_document_id(file)
                        if doc_id:
                            relative_path = Path(root).relative_to(user_base)
                            topic_path = str(relative_path)
                            
                            # 更新索引
                            self.document_index[user_id][doc_id] = {
                                "topic_path": topic_path,
                                "file_name": file,
                                "last_checked": now
                            }
                            found_docs.add(doc_id)
            
            # 清理索引中不存在的文档
            to_remove = []
            for doc_id in self.document_index[user_id]:
                if doc_id not in found_docs:
                    to_remove.append(doc_id)
            
            for doc_id in to_remove:
                del self.document_index[user_id][doc_id]
                
            # 更新刷新时间
            self.last_refresh[user_id] = now
    
    async def save_cache(self, cache_file: str = None) -> bool:
        """保存索引缓存到文件"""
        if not cache_file:
            cache_file = str(self.base_dir / "index_cache.json")
            
        try:
            cache_data = {
                "timestamp": datetime.now().isoformat(),
                "index": self.document_index
            }
            
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f)
                
            return True
        except Exception as e:
            self.logger.error(f"保存索引缓存失败: {e}")
            return False
    
    async def load_cache(self, cache_file: str = None) -> bool:
        """从文件加载索引缓存"""
        if not cache_file:
            cache_file = str(self.base_dir / "index_cache.json")
            
        if not os.path.exists(cache_file):
            return False
            
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                
            self.document_index = cache_data["index"]
            self.logger.info(f"成功从缓存加载索引，时间戳: {cache_data['timestamp']}")
            return True
        except Exception as e:
            self.logger.error(f"加载索引缓存失败: {e}")
            return False
    
    async def create_document(self, user_id: str, topic_path: str, title: str, 
                              content: str = "", metadata: Dict[str, Any] = None) -> str:
        """创建新的 Markdown 文档
        
        Args:
            user_id: 用户ID
            topic_path: 主题路径
            title: 文档标题
            content: 文档内容
            metadata: 额外元数据
            
        Returns:
            新创建的文档ID
        """
        # 1. 生成文档ID
        document_id = str(uuid.uuid4())
        
        # 2. 构建文件路径
        full_topic_path = self.get_topic_path(user_id, topic_path)
        if not full_topic_path.exists():
            full_topic_path.mkdir(parents=True, exist_ok=True)
        
        file_name = self.get_document_file_name(document_id)
        file_path = full_topic_path / file_name
        
        # 3. 准备元数据
        if metadata is None:
            metadata = {}
        
        now = datetime.now().isoformat()
        default_metadata = {
            "title": title,
            "created_at": now,
            "updated_at": now,
            "document_id": document_id,
            "topic_path": topic_path
        }
        
        # 合并用户提供的元数据
        for key, value in metadata.items():
            default_metadata[key] = value
        
        # 4. 创建带有 frontmatter 的文档
        post = frontmatter.Post(content, **default_metadata)
        
        # 5. 写入文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(frontmatter.dumps(post))
            
        return document_id
    
    async def read_document(self, user_id: str, document_id: str) -> Optional[Dict[str, Any]]:
        """读取文档内容和元数据
        
        Args:
            user_id: 用户ID
            document_id: 文档ID
            
        Returns:
            包含内容和元数据的字典，如果文档不存在则返回None
        """
        # 1. 优先从索引获取路径
        topic_path = None
        if self.document_index.get(user_id):
            topic_path = self.document_index[user_id].get(document_id)
        
        # 2. 如果没有找到，再尝试从元数据或文件系统查找
        if not topic_path:
            # 尝试在整个用户目录下查找文档
            document_found = False
            user_base = self.get_user_base(user_id)
            for root, _, files in os.walk(user_base):
                for file in files:
                    if file == self.get_document_file_name(document_id):
                        relative_path = Path(root).relative_to(user_base)
                        topic_path = str(relative_path)
                        document_found = True
                        break
                if document_found:
                    break
            
            if not document_found:
                return None
        
        # 2. 构建完整路径
        file_name = self.get_document_file_name(document_id)
        file_path = self.get_topic_path(user_id, topic_path) / file_name
        
        if not file_path.exists():
            return None
            
        # 3. 读取并解析文件
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                post = frontmatter.load(f)
                
            # 4. 构建返回结果
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
    
    async def update_document(self, user_id: str, document_id: str, 
                              content: Optional[str] = None, 
                              metadata: Optional[Dict[str, Any]] = None) -> bool:
        """更新文档内容或元数据
        
        Args:
            user_id: 用户ID
            document_id: 文档ID
            content: 新的文档内容，None表示不更新
            metadata: 新的元数据，None表示不更新
            
        Returns:
            更新是否成功
        """
        # 1. 读取当前文档
        document = await self.read_document(user_id, document_id)
        if not document:
            return False
            
        # 2. 更新内容或元数据
        current_content = document["content"]
        current_metadata = document["metadata"]
        
        if content is not None:
            current_content = content
            
        if metadata is not None:
            # 更新元数据
            for key, value in metadata.items():
                current_metadata[key] = value
                
        # 始终更新修改时间
        current_metadata["updated_at"] = datetime.now().isoformat()
            
        # 3. 写回文件
        file_path = Path(document["file_path"])
        post = frontmatter.Post(current_content, **current_metadata)
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(frontmatter.dumps(post))
                
            return True
        except Exception as e:
            self.logger.error(f"更新文档失败: {document_id}, 错误: {e}")
            return False
    
    async def delete_document(self, user_id: str, document_id: str) -> bool:
        """删除文档
        
        Args:
            user_id: 用户ID
            document_id: 文档ID
            
        Returns:
            删除是否成功
        """
        # 1. 读取当前文档
        document = await self.read_document(user_id, document_id)
        if not document:
            return False
            
        # 2. 删除文件
        file_path = Path(document["file_path"])
        
        try:
            file_path.unlink()
            return True
        except Exception as e:
            self.logger.error(f"删除文档失败: {document_id}, 错误: {e}")
            return False
    
    def extract_references(self, content: str) -> Dict[str, List[str]]:
        """提取 Markdown 内容中的引用资源
        
        Args:
            content: Markdown 内容
            
        Returns:
            包含不同类型引用的字典，如 {"images": [...], "links": [...]}
        """
        references = {
            "images": [],
            "links": []
        }
        
        # 提取图片链接: ![alt](url)
        image_pattern = r'!\[(.*?)\]\((.*?)\)'
        for match in re.finditer(image_pattern, content):
            image_url = match.group(2).strip()
            if image_url and not image_url.startswith(('http://', 'https://')):
                references["images"].append(image_url)
        
        # 提取普通链接: [text](url)
        link_pattern = r'(?<!!)\[(.*?)\]\((.*?)\)'
        for match in re.finditer(link_pattern, content):
            link_url = match.group(2).strip()
            if link_url and not link_url.startswith(('http://', 'https://')) and link_url.endswith('.md'):
                references["links"].append(link_url)
        
        return references
    
    async def get_document_with_resources(self, user_id: str, document_id: str, 
                                          resolve_references: bool = False) -> Optional[Dict[str, Any]]:
        """读取文档及其引用的资源
        
        Args:
            user_id: 用户ID
            document_id: 文档ID
            resolve_references: 是否解析引用的文档
            
        Returns:
            包含内容、元数据和引用资源的字典
        """
        # 1. 读取基本文档
        document = await self.read_document(user_id, document_id)
        if not document:
            return None
            
        # 2. 提取引用资源
        content = document["content"]
        topic_path = document["metadata"].get("topic_path", "")
        references = self.extract_references(content)
        
        # 3. 处理相对路径
        base_dir = self.get_topic_path(user_id, topic_path)
        
        # 4. 解析图片路径
        resolved_images = []
        for img_path in references["images"]:
            full_path = (base_dir / img_path).resolve()
            if full_path.exists():
                resolved_images.append({
                    "path": img_path,
                    "exists": True,
                    "full_path": str(full_path)
                })
            else:
                resolved_images.append({
                    "path": img_path,
                    "exists": False
                })
        
        # 5. 解析文档引用
        resolved_links = []
        if resolve_references:
            for link_path in references["links"]:
                # 检查是否为文档ID格式
                if link_path.startswith("__id_") and link_path.endswith("__.md"):
                    ref_doc_id = link_path[5:-5]
                    ref_doc = await self.read_document(user_id, ref_doc_id)
                    if ref_doc:
                        resolved_links.append({
                            "path": link_path,
                            "exists": True,
                            "document_id": ref_doc_id,
                            "title": ref_doc["metadata"].get("title", ""),
                            "content": ref_doc["content"] if resolve_references else None
                        })
                    else:
                        resolved_links.append({
                            "path": link_path,
                            "exists": False,
                            "document_id": ref_doc_id
                        })
                else:
                    # 常规相对路径
                    full_path = (base_dir / link_path).resolve()
                    if full_path.exists():
                        try:
                            with open(full_path, 'r', encoding='utf-8') as f:
                                linked_content = f.read()
                                
                            resolved_links.append({
                                "path": link_path,
                                "exists": True,
                                "full_path": str(full_path),
                                "content": linked_content if resolve_references else None
                            })
                        except Exception:
                            resolved_links.append({
                                "path": link_path,
                                "exists": True,
                                "full_path": str(full_path),
                                "error": "无法读取文件内容"
                            })
                    else:
                        resolved_links.append({
                            "path": link_path,
                            "exists": False
                        })
        
        # 6. 组合结果
        result = {
            **document,
            "references": {
                "images": resolved_images,
                "links": resolved_links
            }
        }
        
        return result
        
    async def move_document(self, user_id: str, document_id: str, target_topic_path: str) -> bool:
        """将文档移动到另一个主题
        
        Args:
            user_id: 用户ID
            document_id: 文档ID
            target_topic_path: 目标主题路径
            
        Returns:
            移动是否成功
        """
        # 1. 读取当前文档
        document = await self.read_document(user_id, document_id)
        if not document:
            return False
            
        # 2. 检查目标路径
        target_dir = self.get_topic_path(user_id, target_topic_path)
        if not target_dir.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
            
        # 3. 构建源文件和目标文件路径
        file_name = self.get_document_file_name(document_id)
        source_path = Path(document["file_path"])
        target_path = target_dir / file_name
        
        if target_path.exists():
            self.logger.error(f"目标文件已存在: {target_path}")
            return False
            
        # 4. 执行移动
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.rename(target_path)
            
            # 5. 更新元数据
            metadata = document["metadata"]
            metadata["topic_path"] = target_topic_path
            metadata["updated_at"] = datetime.now().isoformat()
            
            return True
        except Exception as e:
            self.logger.error(f"移动文档失败: {document_id}, 错误: {e}")
            return False

    async def get_topic_structure(self, user_id: str, relative_path: str = "") -> Dict[str, Any]:
        """获取主题结构信息"""
        topic_path = self.path_manager.get_topic_path(user_id, relative_path)
        
        document_ids = []
        subtopics = []
        
        if topic_path.exists():
            for item in topic_path.iterdir():
                if self.path_manager.is_document_file(item):
                    doc_id = self.path_manager.extract_document_id(item)
                    if doc_id:
                        document_ids.append(doc_id)
                elif item.is_dir():
                    subtopics.append(item.name)
        
        return {
            "user_id": user_id,
            "path": relative_path,
            "document_ids": document_ids,
            "subtopics": subtopics
        }

    def list_all_topics(self, user_id: str) -> List[Dict[str, Any]]:
        """列出用户的所有主题"""
        return self._list_topics_recursive(user_id)

    def _list_topics_recursive(self, user_id: str, current_path: str = "") -> List[Dict[str, Any]]:
        """递归获取用户的所有主题信息"""
        topic_info = self.get_topic_structure(user_id, current_path)
        result = [{
            "user_id": user_id,
            "path": current_path or "/",
            "document_count": len(topic_info["document_ids"]),
            "subtopic_count": len(topic_info["subtopics"])
        }]
        
        for subtopic in topic_info["subtopics"]:
            subtopic_path = f"{current_path}/{subtopic}".lstrip("/")
            sub_results = self._list_topics_recursive(user_id, subtopic_path)
            result.extend(sub_results)
        
        return result

    async def create_topic(self, user_id: str, relative_path: str) -> bool:
        """创建主题目录"""
        return self.path_manager.create_topic_dir(user_id, relative_path)

    async def delete_topic(self, user_id: str, relative_path: str, force: bool = False) -> bool:
        """删除主题目录，同步更新文档元数据"""
        if not relative_path:
            return False  # 禁止删除根目录
        
        # 1. 获取要删除的文档ID
        document_ids = self.path_manager.get_physical_document_ids(user_id, relative_path)
        if document_ids and not force:
            return False  # 包含文档且不强制删除
        
        # 2. 如果强制删除，先删除文档
        if document_ids and force:
            for doc_id in document_ids:
                await self.delete_document(user_id, doc_id)
        
        # 3. 执行文件系统操作
        success = self.path_manager.delete_topic_dir(user_id, relative_path)
        
        # 4. 从索引中移除已删除的文档
        async with self.index_lock:
            if user_id in self.document_index:
                for doc_id in document_ids:
                    if doc_id in self.document_index[user_id]:
                        del self.document_index[user_id][doc_id]
        
        return success

    async def rename_topic(self, user_id: str, old_path: str, new_name: str) -> bool:
        """重命名主题目录，同步更新文档元数据"""
        # 执行文件系统操作
        success, new_path = self.path_manager.rename_topic_dir(user_id, old_path, new_name)
        if not success:
            return False
        
        # 更新所有文档的元数据
        document_ids = self.path_manager.get_physical_document_ids(user_id, new_path)
        for doc_id in document_ids:
            document = await self.read_document(user_id, doc_id)
            if document:
                metadata = document["metadata"]
                metadata["topic_path"] = new_path
                await self.update_document(user_id, doc_id, content=None, metadata=metadata)
        
        # 递归更新子主题
        await self.verify_and_repair_document_paths(user_id, new_path)
        
        return True

    async def move_topic(self, user_id: str, source_path: str, target_path: str) -> bool:
        """移动主题到新位置，同步更新文档元数据"""
        # 1. 先获取受影响的文档ID列表
        affected_docs = self.path_manager.get_physical_document_ids(user_id, source_path)
        
        # 2. 执行文件系统操作
        success, new_path = self.path_manager.move_topic_dir(user_id, source_path, target_path)
        if not success:
            return False
        
        # 3. 更新所有受影响文档的元数据
        await self.verify_and_repair_document_paths(user_id, new_path)
        
        # 4. 增量更新索引 - 只更新受影响的文档
        async with self.index_lock:
            if user_id in self.document_index:
                for doc_id in affected_docs:
                    if doc_id in self.document_index[user_id]:
                        # 更新文档路径
                        self.document_index[user_id][doc_id]["topic_path"] = new_path
                        self.document_index[user_id][doc_id]["last_checked"] = datetime.now().timestamp()
        
        return True

    async def copy_topic(self, user_id: str, source_path: str, target_path: str) -> bool:
        """复制主题到新位置，为新文档创建元数据"""
        # 执行文件系统操作
        success, new_path = self.path_manager.copy_topic_dir(user_id, source_path, target_path)
        if not success:
            return False
        
        # 更新所有文档的元数据
        await self.verify_and_repair_document_paths(user_id, new_path)
        
        return True

    async def merge_topics(self, user_id: str, source_path: str, target_path: str, overwrite: bool = False) -> bool:
        """合并主题，同步更新文档元数据"""
        # 1. 先获取受影响的文档ID列表
        affected_docs = self.path_manager.get_physical_document_ids(user_id, source_path)
        
        # 2. 执行文件系统操作
        success = self.path_manager.merge_topic_dirs(user_id, source_path, target_path, overwrite)
        if not success:
            return False
        
        # 3. 更新所有受影响文档的元数据
        await self.verify_and_repair_document_paths(user_id, target_path)
        
        # 4. 增量更新索引 - 只更新受影响的文档
        async with self.index_lock:
            if user_id in self.document_index:
                for doc_id in affected_docs:
                    if doc_id in self.document_index[user_id]:
                        # 更新文档路径
                        self.document_index[user_id][doc_id]["topic_path"] = target_path
                        self.document_index[user_id][doc_id]["last_checked"] = datetime.now().timestamp()
        
        return True

    async def verify_and_repair_document_paths(self, user_id: str, topic_path: str = "") -> None:
        """验证主题下所有文档的元数据与文件系统位置一致性，并自动修复"""
        # 获取文件系统中的文档ID
        fs_document_ids = self.path_manager.get_physical_document_ids(user_id, topic_path)
        
        # 更新所有文档的元数据
        for doc_id in fs_document_ids:
            document = await self.read_document(user_id, doc_id)
            if document:
                metadata = document["metadata"]
                # 仅当元数据中的topic_path不匹配时更新
                if metadata.get("topic_path") != topic_path:
                    self.logger.info(f"修复文档路径: {doc_id} 从 {metadata.get('topic_path')} 到 {topic_path}")
                    metadata["topic_path"] = topic_path
                    await self.update_document(user_id, doc_id, content=None, metadata=metadata)
        
        # 递归处理子主题
        topic_structure = self.path_manager.get_topic_structure(user_id, topic_path)
        for subtopic in topic_structure["subtopics"]:
            subtopic_path = f"{topic_path}/{subtopic}".lstrip("/")
            await self.verify_and_repair_document_paths(user_id, subtopic_path)
