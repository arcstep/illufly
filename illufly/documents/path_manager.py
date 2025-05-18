import logging
import shutil
from pathlib import Path
from typing import Dict, Any, List, Tuple

class PathManager:
    """路径管理器 - 处理所有文件系统操作"""
    
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
    
    # ==== 基础路径操作 ====
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
    
    # ==== 文件识别与命名 ====
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
            
        if name.startswith("__id_") and name.endswith("__.md"):
            return name[5:-5]  # 去掉 '__id_' 和 '__.md'
        return None

    def get_document_file_name(self, document_id: str) -> str:
        """根据document_id构造标准文件名"""
        return f"__id_{document_id}__.md"
    
    # ==== 路径结构处理 ====
    def parse_path_structure(self, path: str) -> Dict[str, Any]:
        """解析路径结构，识别其中的主题和文档"""
        if not path:
            return {"topics": [], "document_id": None}
        
        parts = path.split("/")
        topics = []
        document_id = None
        
        for part in parts:
            if part.startswith("__id_") and part.endswith("__.md"):
                document_id = part[5:-5]
            elif part:  # 忽略空部分
                topics.append(part)
        
        return {
            "topics": topics,
            "document_id": document_id
        }

    def create_path_from_structure(self, topics: List[str], document_id: str = None) -> str:
        """根据主题列表和文档ID构建路径"""
        path_parts = topics.copy()
        
        if document_id:
            path_parts.append(self.get_document_file_name(document_id))
        
        return "/".join(path_parts)
    
    def get_topic_path_text(self, relative_path: str) -> str:
        """获取主题的可读文本表示"""
        structure = self.parse_path_structure(relative_path)
        return "/".join(structure["topics"])

    # ==== 主题结构操作 ====
    def get_physical_document_ids(self, user_id: str, relative_path: str = "") -> List[str]:
        """获取文件系统中主题下的所有文档ID"""
        topic_path = self.get_topic_path(user_id, relative_path)
        document_ids = []
        
        if topic_path.exists():
            for item in topic_path.iterdir():
                if self.is_document_file(item):
                    doc_id = self.extract_document_id(item)
                    if doc_id:
                        document_ids.append(doc_id)
        
        return document_ids
    
    def get_topic_structure(self, user_id: str, relative_path: str = "") -> Dict[str, Any]:
        """获取主题结构信息"""
        topic_path = self.get_topic_path(user_id, relative_path)
        
        document_ids = []
        subtopics = []
        
        if topic_path.exists():
            for item in topic_path.iterdir():
                if self.is_document_file(item):
                    doc_id = self.extract_document_id(item)
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
        
    def get_all_topic_document_ids(self, user_id: str, relative_path: str = "", recursive: bool = False) -> List[str]:
        """获取主题下的所有文档ID，可选递归获取子主题下的文档"""
        # 获取当前主题的文档ID
        document_ids = self.get_physical_document_ids(user_id, relative_path)
        
        # 如果不需要递归，直接返回结果
        if not recursive:
            return document_ids
        
        # 递归获取所有子主题中的文档
        topic_structure = self.get_topic_structure(user_id, relative_path)
        for subtopic_name in topic_structure["subtopics"]:
            subtopic_path = f"{relative_path}/{subtopic_name}".lstrip("/")
            sub_doc_ids = self.get_all_topic_document_ids(user_id, subtopic_path, recursive=True)
            document_ids.extend(sub_doc_ids)
        
        return document_ids
    
    # ==== 主题目录操作 ====
    def create_topic_dir(self, user_id: str, relative_path: str) -> bool:
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
    
    def delete_topic_dir(self, user_id: str, relative_path: str) -> bool:
        """删除主题目录（仅文件系统操作）"""
        if not relative_path:
            return False  # 禁止删除根目录
            
        topic_path = self.get_topic_path(user_id, relative_path)
        if not topic_path.exists():
            return True  # 目录不存在，视为成功
            
        try:
            shutil.rmtree(topic_path)
            return True
        except Exception as e:
            self.logger.error(f"删除主题目录失败: {user_id}/{relative_path}, 错误: {e}")
            return False
    
    def rename_topic_dir(self, user_id: str, old_path: str, new_name: str) -> Tuple[bool, str]:
        """重命名主题目录（仅文件系统操作）
        
        Returns:
            (成功与否, 新路径)
        """
        if not old_path:
            return False, ""  # 禁止重命名根目录
            
        old_topic_path = self.get_topic_path(user_id, old_path)
        if not old_topic_path.exists():
            return False, ""
            
        parent_path = "/".join(old_path.split("/")[:-1])
        new_path = f"{parent_path}/{new_name}" if parent_path else new_name
        new_topic_path = self.get_topic_path(user_id, new_path)
        
        if new_topic_path.exists():
            return False, ""  # 目标路径已存在
        
        try:
            old_topic_path.rename(new_topic_path)
            return True, new_path
        except Exception as e:
            self.logger.error(f"重命名主题目录失败: {user_id}/{old_path} -> {new_name}, 错误: {e}")
            return False, ""
    
    def move_topic_dir(self, user_id: str, source_path: str, target_path: str) -> Tuple[bool, str]:
        """移动主题目录（仅文件系统操作）
        
        Returns:
            (成功与否, 新路径)
        """
        if not source_path:
            return False, ""  # 禁止移动根目录
            
        source_topic_path = self.get_topic_path(user_id, source_path)
        if not source_topic_path.exists():
            return False, ""
            
        target_topic_path = self.get_topic_path(user_id, target_path)
        
        # 确保目标目录存在
        if not target_topic_path.exists():
            target_topic_path.mkdir(parents=True, exist_ok=True)
            
        # 构建新的目标路径
        source_name = source_path.split("/")[-1]
        new_path = f"{target_path}/{source_name}" if target_path else source_name
        new_full_path = target_topic_path / source_name
        
        if new_full_path.exists():
            return False, ""  # 目标位置已存在同名目录
            
        try:
            shutil.move(str(source_topic_path), str(new_full_path))
            return True, new_path
        except Exception as e:
            self.logger.error(f"移动主题目录失败: {user_id}/{source_path} -> {target_path}, 错误: {e}")
            return False, ""
            
    def copy_topic_dir(self, user_id: str, source_path: str, target_path: str) -> Tuple[bool, str]:
        """复制主题目录（仅文件系统操作）
        
        Returns:
            (成功与否, 新路径)
        """
        if not source_path:
            return False, ""  # 禁止复制根目录
            
        source_topic_path = self.get_topic_path(user_id, source_path)
        if not source_topic_path.exists():
            return False, ""
            
        target_topic_path = self.get_topic_path(user_id, target_path)
        
        # 确保目标目录存在
        if not target_topic_path.exists():
            target_topic_path.mkdir(parents=True, exist_ok=True)
            
        # 构建新的目标路径
        source_name = source_path.split("/")[-1]
        new_path = f"{target_path}/{source_name}" if target_path else source_name
        new_full_path = target_topic_path / source_name
        
        if new_full_path.exists():
            return False, ""  # 目标位置已存在同名目录
            
        try:
            shutil.copytree(str(source_topic_path), str(new_full_path))
            return True, new_path
        except Exception as e:
            self.logger.error(f"复制主题目录失败: {user_id}/{source_path} -> {target_path}, 错误: {e}")
            return False, ""
            
    def merge_topic_dirs(self, user_id: str, source_path: str, target_path: str, overwrite: bool = False) -> bool:
        """合并主题目录（仅文件系统操作）"""
        source_topic_path = self.get_topic_path(user_id, source_path)
        target_topic_path = self.get_topic_path(user_id, target_path)
        
        if not source_topic_path.exists() or not target_topic_path.exists():
            return False
            
        try:
            # 遍历源目录的所有内容
            for item in source_topic_path.iterdir():
                dest_path = target_topic_path / item.name
                
                if item.is_dir():
                    # 子主题处理 - 递归合并
                    if dest_path.exists():
                        rel_source = f"{source_path}/{item.name}" if source_path else item.name
                        rel_target = f"{target_path}/{item.name}" if target_path else item.name
                        self.merge_topic_dirs(user_id, rel_source, rel_target, overwrite)
                    else:
                        shutil.copytree(str(item), str(dest_path))
                elif self.is_document_file(item):
                    # 文档文件处理
                    if dest_path.exists():
                        if overwrite:
                            dest_path.unlink()
                            shutil.copy2(item, dest_path)
                    else:
                        shutil.copy2(item, dest_path)
                else:
                    # 普通文件处理
                    if dest_path.exists() and not overwrite:
                        continue
                    shutil.copy2(item, dest_path)
            
            return True
        except Exception as e:
            self.logger.error(f"合并主题目录失败: {user_id}/{source_path} -> {target_path}, 错误: {e}")
            return False
