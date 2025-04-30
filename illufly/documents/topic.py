import logging
from pathlib import Path
from typing import Dict, Any, List

class TopicManager:
    """主题管理器 - 支持多用户隔离的目录结构"""
    
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
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
    
    def get_topic_structure(self, user_id: str, relative_path: str = "") -> Dict[str, Any]:
        """获取主题结构信息
        
        Args:
            user_id: 用户ID
            relative_path: 主题相对路径
            
        Returns:
            包含document_ids列表和subtopics列表的字典
        """
        topic_path = self.get_topic_path(user_id, relative_path)
        
        # 文档ID列表（包含meta.json的目录）
        document_ids = []
        # 子主题列表（不包含meta.json的目录）
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
        
        # 递归处理子主题
        for subtopic in topic_info["subtopics"]:
            subtopic_path = f"{current_path}/{subtopic}".lstrip("/")
            sub_results = self._list_topics_recursive(user_id, subtopic_path)
            result.extend(sub_results)
        
        return result
    
    def get_document_ids_in_topic(self, user_id: str, relative_path: str = "") -> List[str]:
        """获取主题下的所有文档ID"""
        return self.get_topic_structure(user_id, relative_path)["document_ids"]
    
    def create_topic(self, user_id: str, relative_path: str) -> bool:
        """创建主题目录
        
        Args:
            user_id: 用户ID
            relative_path: 要创建的主题相对路径
            
        Returns:
            bool: 创建是否成功
        """
        if not relative_path:
            return False  # 根目录已存在，无需创建
            
        topic_path = self.get_topic_path(user_id, relative_path)
        if topic_path.exists():
            return True  # 目录已存在，视为成功
            
        try:
            topic_path.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            logging.error(f"创建主题目录失败: {user_id}/{relative_path}, 错误: {e}")
            return False
    
    def delete_topic(self, user_id: str, relative_path: str, force: bool = False) -> bool:
        """删除主题目录
        
        Args:
            user_id: 用户ID
            relative_path: 要删除的主题相对路径
            force: 是否强制删除(包含文档目录)
            
        Returns:
            bool: 删除是否成功
        """
        if not relative_path:
            return False  # 禁止删除根目录
            
        topic_path = self.get_topic_path(user_id, relative_path)
        if not topic_path.exists():
            return True  # 目录不存在，视为成功
            
        # 检查是否包含文档
        structure = self.get_topic_structure(user_id, relative_path)
        if structure["document_ids"] and not force:
            return False  # 包含文档且不强制删除
            
        try:
            import shutil
            shutil.rmtree(topic_path)
            return True
        except Exception as e:
            logging.error(f"删除主题目录失败: {user_id}/{relative_path}, 错误: {e}")
            return False
    
    def rename_topic(self, user_id: str, old_path: str, new_name: str) -> bool:
        """重命名主题目录
        
        Args:
            user_id: 用户ID
            old_path: 原主题路径
            new_name: 新的目录名(不是完整路径)
            
        Returns:
            bool: 重命名是否成功
        """
        if not old_path:
            return False  # 禁止重命名根目录
            
        old_topic_path = self.get_topic_path(user_id, old_path)
        if not old_topic_path.exists():
            return False
            
        parent_path = old_topic_path.parent
        new_topic_path = parent_path / new_name
        
        if new_topic_path.exists():
            return False  # 目标路径已存在
            
        try:
            old_topic_path.rename(new_topic_path)
            return True
        except Exception as e:
            logging.error(f"重命名主题失败: {user_id}/{old_path} -> {new_name}, 错误: {e}")
            return False
    
    def move_topic(self, user_id: str, source_path: str, target_path: str) -> bool:
        """移动主题到另一个位置
        
        Args:
            user_id: 用户ID
            source_path: 源主题路径
            target_path: 目标主题路径(父级目录)
            
        Returns:
            bool: 移动是否成功
        """
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
        new_path = target_topic_path / source_topic_path.name
        
        if new_path.exists():
            return False  # 目标位置已存在同名目录
            
        try:
            import shutil
            shutil.move(str(source_topic_path), str(new_path))
            return True
        except Exception as e:
            logging.error(f"移动主题失败: {user_id}/{source_path} -> {target_path}, 错误: {e}")
            return False
    
    def copy_topic(self, user_id: str, source_path: str, target_path: str) -> bool:
        """复制主题到另一个位置
        
        Args:
            user_id: 用户ID
            source_path: 源主题路径
            target_path: 目标主题路径(父级目录)
            
        Returns:
            bool: 复制是否成功
        """
        if not source_path:
            return False  # 禁止复制根目录
            
        source_topic_path = self.get_topic_path(user_id, source_path)
        if not source_topic_path.exists():
            return False
            
        target_topic_path = self.get_topic_path(user_id, target_path)
        
        # 确保目标目录存在
        if not target_topic_path.exists():
            target_topic_path.mkdir(parents=True, exist_ok=True)
            
        # 构建新的目标路径(目标目录+源目录名)
        new_path = target_topic_path / source_topic_path.name
        
        if new_path.exists():
            return False  # 目标位置已存在同名目录
            
        try:
            import shutil
            shutil.copytree(str(source_topic_path), str(new_path))
            return True
        except Exception as e:
            logging.error(f"复制主题失败: {user_id}/{source_path} -> {target_path}, 错误: {e}")
            return False
            
    def merge_topics(self, user_id: str, source_path: str, target_path: str, overwrite: bool = False) -> bool:
        """合并两个主题目录
        
        Args:
            user_id: 用户ID
            source_path: 源主题路径
            target_path: 目标主题路径
            overwrite: 发生冲突时是否覆盖目标文件
            
        Returns:
            bool: 合并是否成功
        """
        source_topic_path = self.get_topic_path(user_id, source_path)
        target_topic_path = self.get_topic_path(user_id, target_path)
        
        if not source_topic_path.exists() or not target_topic_path.exists():
            return False
            
        try:
            import shutil
            # 遍历源目录的所有内容
            for item in source_topic_path.iterdir():
                dest_path = target_topic_path / item.name
                
                if item.is_dir():
                    if dest_path.exists():
                        if self.is_document_dir(item):
                            # 文档目录冲突，根据overwrite决定
                            if overwrite:
                                shutil.rmtree(dest_path)
                                shutil.copytree(item, dest_path)
                        else:
                            # 子主题目录，递归合并
                            rel_source = f"{source_path}/{item.name}" if source_path else item.name
                            rel_target = f"{target_path}/{item.name}" if target_path else item.name
                            self.merge_topics(user_id, rel_source, rel_target, overwrite)
                    else:
                        # 目标不存在，直接复制
                        shutil.copytree(item, dest_path)
                else:
                    # 文件处理
                    if dest_path.exists() and not overwrite:
                        continue  # 跳过已存在的文件
                    shutil.copy2(item, dest_path)
            
            return True
        except Exception as e:
            logging.error(f"合并主题失败: {user_id}/{source_path} -> {target_path}, 错误: {e}")
            return False
    
    def search_topics(self, user_id: str, keyword: str) -> List[Dict[str, Any]]:
        """搜索包含关键字的主题
        
        Args:
            user_id: 用户ID
            keyword: 搜索关键字
            
        Returns:
            List[Dict]: 匹配的主题列表
        """
        all_topics = self.list_all_topics(user_id)
        
        # 简单的名称匹配
        return [
            topic for topic in all_topics 
            if keyword.lower() in topic["path"].lower()
        ]

    def extract_document_id(self, dir_path: Path) -> str:
        """从文档目录路径提取document_id"""
        name = dir_path.name
        if self.is_document_dir(dir_path):
            return name[5:-2]  # 去掉 '__id_' 和 '__'
        return None

    def get_document_folder_name(self, document_id: str) -> str:
        """根据document_id构造标准目录名"""
        return f"__id_{document_id}__"
