import logging
import shutil
from pathlib import Path
from typing import Dict, Any, List, Set, Optional

class TopicManager:
    """主题管理器 - 支持多用户隔离的目录结构"""
    
    def __init__(self, base_dir: str, meta_manager=None):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.meta_manager = meta_manager
        self.logger = logging.getLogger(__name__)
    
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
    
    def is_document_dir(self, dir_path: Path) -> bool:
        """判断目录是否为文档目录（使用__id_{document_id}__命名规则）"""
        return dir_path.name.startswith("__id_") and dir_path.name.endswith("__")
    
    def _get_physical_document_ids(self, user_id: str, relative_path: str = "") -> List[str]:
        """获取文件系统中主题下的所有文档ID"""
        topic_path = self.get_topic_path(user_id, relative_path)
        document_ids = []
        
        if topic_path.exists():
            for item in topic_path.iterdir():
                if item.is_dir() and self.is_document_dir(item):
                    doc_id = self.extract_document_id(item)
                    if doc_id:
                        document_ids.append(doc_id)
        
        return document_ids
    
    async def _update_document_topic_path(self, user_id: str, document_id: str, new_topic_path: str) -> bool:
        """更新文档的主题路径元数据"""
        if not self.meta_manager:
            return False
            
        result = await self.meta_manager.update_metadata(
            user_id, 
            document_id, 
            {"topic_path": new_topic_path}
        )
        return result is not None
    
    async def _batch_update_document_metadata(self, user_id: str, document_ids: List[str], new_topic_path: str) -> Dict[str, bool]:
        """批量更新多个文档的主题路径"""
        results = {}
        for doc_id in document_ids:
            success = await self._update_document_topic_path(user_id, doc_id, new_topic_path)
            results[doc_id] = success
        return results
    
    def get_topic_structure(self, user_id: str, relative_path: str = "") -> Dict[str, Any]:
        """获取主题结构信息"""
        topic_path = self.get_topic_path(user_id, relative_path)
        
        document_ids = []
        subtopics = []
        
        if topic_path.exists():
            for item in topic_path.iterdir():
                if item.is_dir():
                    if self.is_document_dir(item):
                        document_ids.append(item.name)
                    else:
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
    
    def get_document_ids_in_topic(self, user_id: str, relative_path: str = "") -> List[str]:
        """获取主题下的所有文档ID"""
        return self._get_physical_document_ids(user_id, relative_path)
    
    def create_topic(self, user_id: str, relative_path: str) -> bool:
        """创建主题目录"""
        if not relative_path:
            return False  # 根目录已存在，无需创建
            
        topic_path = self.get_topic_path(user_id, relative_path)
        if topic_path.exists():
            return True  # 目录已存在，视为成功
            
        try:
            topic_path.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            self.logger.error(f"创建主题目录失败: {user_id}/{relative_path}, 错误: {e}")
            return False
    
    async def delete_topic(self, user_id: str, relative_path: str, force: bool = False) -> bool:
        """删除主题目录，同步更新元数据"""
        if not relative_path:
            return False  # 禁止删除根目录
            
        topic_path = self.get_topic_path(user_id, relative_path)
        if not topic_path.exists():
            return True  # 目录不存在，视为成功
            
        # 检查是否包含文档
        document_ids = self._get_physical_document_ids(user_id, relative_path)
        if document_ids and not force:
            return False  # 包含文档且不强制删除
            
        # 如果强制删除，先处理元数据
        if document_ids and force and self.meta_manager:
            for doc_id in document_ids:
                await self.meta_manager.delete_document(user_id, doc_id)
        
        try:
            shutil.rmtree(topic_path)
            return True
        except Exception as e:
            self.logger.error(f"删除主题目录失败: {user_id}/{relative_path}, 错误: {e}")
            return False
    
    async def rename_topic(self, user_id: str, old_path: str, new_name: str) -> bool:
        """重命名主题目录，同步更新文档元数据"""
        if not old_path:
            return False  # 禁止重命名根目录
            
        old_topic_path = self.get_topic_path(user_id, old_path)
        if not old_topic_path.exists():
            return False
            
        parent_path = "/".join(old_path.split("/")[:-1])
        new_path = f"{parent_path}/{new_name}" if parent_path else new_name
        new_topic_path = self.get_topic_path(user_id, new_path)
        
        if new_topic_path.exists():
            return False  # 目标路径已存在
        
        try:
            # 1. 先获取所有文档ID
            document_ids = self._get_physical_document_ids(user_id, old_path)
            
            # 2. 执行重命名
            old_topic_path.rename(new_topic_path)
            
            # 3. 更新所有文档的元数据（包括子主题的）
            if self.meta_manager:
                # 更新主题中的文档
                await self._batch_update_document_metadata(user_id, document_ids, new_path)
                
                # 递归更新子主题中的文档
                for subtopic in self.get_topic_structure(user_id, new_path)["subtopics"]:
                    subtopic_path = f"{new_path}/{subtopic}"
                    await self.verify_and_repair_document_paths(user_id, subtopic_path)
                
            return True
        except Exception as e:
            self.logger.error(f"重命名主题失败: {user_id}/{old_path} -> {new_name}, 错误: {e}")
            return False
    
    async def move_topic(self, user_id: str, source_path: str, target_path: str) -> bool:
        """移动主题到新位置，同步更新文档元数据"""
        if not source_path:
            return False  # 禁止移动根目录
            
        source_topic_path = self.get_topic_path(user_id, source_path)
        if not source_topic_path.exists():
            return False
            
        target_topic_path = self.get_topic_path(user_id, target_path)
        
        # 确保目标目录存在
        if not target_topic_path.exists():
            target_topic_path.mkdir(parents=True, exist_ok=True)
            
        # 构建新的目标路径(目标目录+源目录名)
        source_name = source_path.split("/")[-1]
        new_path = f"{target_path}/{source_name}" if target_path else source_name
        new_full_path = target_topic_path / source_name
        
        if new_full_path.exists():
            return False  # 目标位置已存在同名目录
            
        try:
            # 1. 先获取所有文档ID（包括子主题）
            all_document_ids = []
            for topic in self._list_topics_recursive(user_id, source_path):
                topic_relative_path = topic["path"]
                doc_ids = self._get_physical_document_ids(user_id, topic_relative_path)
                all_document_ids.extend(doc_ids)
            
            # 2. 执行移动
            shutil.move(str(source_topic_path), str(new_full_path))
            
            # 3. 更新所有文档的元数据
            if self.meta_manager:
                # 修复新主题下所有文档的路径
                await self.verify_and_repair_document_paths(user_id, new_path)
            
            return True
        except Exception as e:
            self.logger.error(f"移动主题失败: {user_id}/{source_path} -> {target_path}, 错误: {e}")
            return False
    
    async def copy_topic(self, user_id: str, source_path: str, target_path: str) -> bool:
        """复制主题到新位置，为新文档创建元数据"""
        if not source_path:
            return False  # 禁止复制根目录
            
        source_topic_path = self.get_topic_path(user_id, source_path)
        if not source_topic_path.exists():
            return False
            
        target_topic_path = self.get_topic_path(user_id, target_path)
        
        # 确保目标目录存在
        if not target_topic_path.exists():
            target_topic_path.mkdir(parents=True, exist_ok=True)
            
        # 构建新的目标路径
        source_name = source_path.split("/")[-1]
        new_path = f"{target_path}/{source_name}" if target_path else source_name
        new_full_path = target_topic_path / source_name
        
        if new_full_path.exists():
            return False  # 目标位置已存在同名目录
            
        try:
            # 复制目录结构
            shutil.copytree(str(source_topic_path), str(new_full_path))
            
            # 复制文档后修复元数据（这里文档ID相同但路径不同，需要创建新元数据）
            if self.meta_manager:
                # 获取新复制的所有文档ID
                copied_doc_ids = self._get_physical_document_ids(user_id, new_path)
                
                # 注意：这里需要为每个复制的文档创建新的document_id和元数据
                # 这需要物理重命名文档目录并创建新元数据
                # 此功能较复杂，实际实现时可能需要额外开发
                self.logger.warning(f"复制主题成功，但元数据同步需要单独处理: {new_path}")
            
            return True
        except Exception as e:
            self.logger.error(f"复制主题失败: {user_id}/{source_path} -> {target_path}, 错误: {e}")
            return False
    
    async def merge_topics(self, user_id: str, source_path: str, target_path: str, overwrite: bool = False) -> bool:
        """合并主题，同步更新文档元数据"""
        source_topic_path = self.get_topic_path(user_id, source_path)
        target_topic_path = self.get_topic_path(user_id, target_path)
        
        if not source_topic_path.exists() or not target_topic_path.exists():
            return False
            
        try:
            # 记录合并前文件系统状态
            target_docs_before = set(self._get_physical_document_ids(user_id, target_path))
            
            # 遍历源目录的所有内容
            for item in source_topic_path.iterdir():
                dest_path = target_topic_path / item.name
                
                if item.is_dir():
                    if self.is_document_dir(item):
                        # 文档目录处理
                        if dest_path.exists():
                            if overwrite:
                                shutil.rmtree(dest_path)
                                shutil.copytree(item, dest_path)
                        else:
                            shutil.copytree(item, dest_path)
                    else:
                        # 子主题处理 - 递归合并
                        if dest_path.exists():
                            rel_source = f"{source_path}/{item.name}" if source_path else item.name
                            rel_target = f"{target_path}/{item.name}" if target_path else item.name
                            await self.merge_topics(user_id, rel_source, rel_target, overwrite)
                        else:
                            shutil.copytree(item, dest_path)
                else:
                    # 普通文件处理
                    if dest_path.exists() and not overwrite:
                        continue
                    shutil.copy2(item, dest_path)
            
            # 获取合并后的文档状态并更新元数据
            if self.meta_manager:
                # 修复目标路径下的所有文档元数据
                await self.verify_and_repair_document_paths(user_id, target_path)
            
            return True
        except Exception as e:
            self.logger.error(f"合并主题失败: {user_id}/{source_path} -> {target_path}, 错误: {e}")
            return False
    
    def search_topics(self, user_id: str, keyword: str) -> List[Dict[str, Any]]:
        """搜索包含关键字的主题"""
        all_topics = self.list_all_topics(user_id)
        return [
            topic for topic in all_topics 
            if keyword.lower() in topic["path"].lower()
        ]

    def extract_document_id(self, dir_path: Path) -> str:
        """从文档目录路径提取document_id"""
        name = dir_path.name if isinstance(dir_path, Path) else dir_path
        if isinstance(name, Path):
            name = name.name
            
        if name.startswith("__id_") and name.endswith("__"):
            return name[5:-2]  # 去掉 '__id_' 和 '__'
        return None

    def get_document_folder_name(self, document_id: str) -> str:
        """根据document_id构造标准目录名"""
        return f"__id_{document_id}__"
    
    async def verify_and_repair_document_paths(self, user_id: str, topic_path: str = ""):
        """验证主题下所有文档的元数据与文件系统位置一致性，并自动修复"""
        if not self.meta_manager:
            self.logger.warning("无法修复文档路径：未提供元数据管理器")
            return
            
        # 获取文件系统中的文档ID
        fs_document_ids = self._get_physical_document_ids(user_id, topic_path)
        
        # 更新所有文档的元数据
        for doc_id in fs_document_ids:
            meta = await self.meta_manager.get_metadata(user_id, doc_id)
            if meta:
                # 仅当元数据中的topic_path不匹配时更新
                if meta.get("topic_path") != topic_path:
                    self.logger.info(f"修复文档路径: {doc_id} 从 {meta.get('topic_path')} 到 {topic_path}")
                    await self.meta_manager.update_metadata(
                        user_id, doc_id, {"topic_path": topic_path}
                    )
            else:
                self.logger.warning(f"发现孤立文档目录，无对应元数据: {user_id}/{topic_path}/{self.get_document_folder_name(doc_id)}")
        
        # 递归处理子主题
        topic_structure = self.get_topic_structure(user_id, topic_path)
        for subtopic in topic_structure["subtopics"]:
            subtopic_path = f"{topic_path}/{subtopic}".lstrip("/")
            await self.verify_and_repair_document_paths(user_id, subtopic_path)

    async def get_all_documents_in_topic(self, user_id: str, topic_path: str = "", recursive: bool = False) -> List[str]:
        """获取主题及其子主题中的所有文档ID
        
        Args:
            user_id: 用户ID
            topic_path: 主题路径
            recursive: 是否递归获取子主题中的文档
            
        Returns:
            所有文档ID列表
        """
        # 获取当前主题的文档ID
        document_ids = self._get_physical_document_ids(user_id, topic_path)
        
        # 如果不需要递归，直接返回结果
        if not recursive:
            return document_ids
        
        # 递归获取所有子主题中的文档
        topic_structure = self.get_topic_structure(user_id, topic_path)
        for subtopic_name in topic_structure["subtopics"]:
            subtopic_path = f"{topic_path}/{subtopic_name}".lstrip("/")
            # 递归调用获取子主题文档
            sub_doc_ids = await self.get_all_documents_in_topic(user_id, subtopic_path, recursive=True)
            document_ids.extend(sub_doc_ids)
        
        return document_ids