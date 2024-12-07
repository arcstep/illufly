from pathlib import Path
import json
from typing import Dict, List, Union
from .base import BaseKnowledge
from ...config import get_env

class LocalFileKnowledge(BaseKnowledge):
    def __init__(self, directory: Union[str, Path]=None):
        """初始化本地文件知识库
        
        Args:
            directory: 知识库存储目录
        """
        super().__init__()
        self.directory = Path(directory or get_env("ILLUFLY_CHAT_LEARN"))
        self.directory.mkdir(parents=True, exist_ok=True)
        self._load()
    
    def _load(self) -> None:
        """从目录递归加载所有知识条目"""
        # 初始化存储
        self.store = {}
        self.tag_index = {}
        
        # 递归遍历所有json文件，排除隐藏文件
        for json_file in self.directory.rglob("*.json"):
            # 跳过隐藏文件和标签索引文件
            if json_file.name.startswith('.') or json_file.name == "tag_index.json":
                continue
            # 检查路径中是否包含隐藏文件夹
            if any(part.startswith('.') for part in json_file.parts):
                continue
            
            with open(json_file, "r", encoding="utf-8") as f:
                try:
                    doc = json.load(f)
                    knowledge_id = json_file.stem  # 使用文件名作为knowledge_id
                    
                    # 确保数据格式正确
                    if isinstance(doc, dict) and 'text' in doc and 'meta' in doc:
                        self.store[knowledge_id] = doc
                        # 更新标签索引
                        if 'tags' in doc['meta']:
                            for tag in doc['meta']['tags']:
                                if tag not in self.tag_index:
                                    self.tag_index[tag] = set()
                                self.tag_index[tag].add(knowledge_id)
                except json.JSONDecodeError:
                    continue  # 跳过无效的JSON文件
        
        # 加载标签索引（如果存在）
        tag_index_file = self.directory / "tag_index.json"
        if tag_index_file.exists():
            with open(tag_index_file, "r", encoding="utf-8") as f:
                tag_data = json.load(f)
                self.tag_index = {
                    tag: set(ids) for tag, ids in tag_data.items()
                }
    
    def _save(self) -> None:
        """保存所有知识条目到对应的子文件夹"""
        # 确保根目录存在
        self.directory.mkdir(parents=True, exist_ok=True)
        
        # 保存标签索引
        tag_index_data = {
            tag: list(ids) for tag, ids in self.tag_index.items()
        }
        with open(self.directory / "tag_index.json", "w", encoding="utf-8") as f:
            json.dump(tag_index_data, f, ensure_ascii=False, indent=2)
    
    def _get_knowledge_path(self, knowledge_id: str, tags: List[str] = None) -> Path:
        """获取知识条目的存储路径
        
        Args:
            knowledge_id: 知识条目ID
            tags: 标签列表，第一个标签用作子文件夹路径
        """
        if tags and tags[0]:
            # 使用第一个标签作为子文件夹路径
            subfolder = self.directory / tags[0]
            subfolder.mkdir(parents=True, exist_ok=True)
            return subfolder / f"{knowledge_id}.json"
        return self.directory / f"{knowledge_id}.json"
    
    def add(self, text: str, tags: List[str]=None, summary: str="", source: str=None) -> str:
        """重写add方法，添加到对应子文件夹，避免重复"""
        # 先调用父类的add方法，它会处理重复检查
        knowledge_id = super().add(text, tags, summary, source)
        
        # 检查是否是新增的知识条目
        # 如果knowledge_id已经有对应的文件，说明是重复的，直接返回
        existing_path = self._get_knowledge_path(knowledge_id, tags)
        if existing_path.exists():
            return knowledge_id
        
        # 获取存储路径并保存
        knowledge_path = self._get_knowledge_path(knowledge_id, tags)
        # 确保父目录存在
        knowledge_path.parent.mkdir(parents=True, exist_ok=True)
        with open(knowledge_path, "w", encoding="utf-8") as f:
            json.dump(self.store[knowledge_id], f, ensure_ascii=False, indent=2)
        self._save()  # 更新标签索引
        return knowledge_id
    
    def update(
        self,
        knowledge_id: str,
        text: str=None,
        tags: List[str]=None,
        summary: str=None,
        source: str=None
    ) -> bool:
        """重写update方法，更新对应子文件夹中的文件，避免重复"""
        # 获取旧标签，用于后续文件移动
        old_tags = self.store[knowledge_id].get("meta", {}).get("tags", []) if knowledge_id in self.store else None
        
        # 调用父类的update方法，它会处理重复检查
        result = super().update(knowledge_id, text, tags, summary, source)
        
        if result:
            # 如果标签发生变化，可能需要移动文件
            if old_tags and old_tags[0]:
                old_path = self._get_knowledge_path(knowledge_id, old_tags)
                if old_path.exists():
                    old_path.unlink()
            
            # 保存到新位置
            new_tags = self.store[knowledge_id].get("meta", {}).get("tags", [])
            knowledge_path = self._get_knowledge_path(knowledge_id, new_tags)
            
            # 检查新路径是否已存在其他知识条目
            if knowledge_path.exists() and knowledge_path.stem != knowledge_id:
                return False
            
            # 确保父目录存在
            knowledge_path.parent.mkdir(parents=True, exist_ok=True)
            with open(knowledge_path, "w", encoding="utf-8") as f:
                json.dump(self.store[knowledge_id], f, ensure_ascii=False, indent=2)
            self._save()  # 更新标签索引
        return result
    
    def delete(self, knowledge_id: str) -> bool:
        """重写delete方法，删除对应子文件夹中的文件"""
        if knowledge_id in self.store:
            tags = self.store[knowledge_id].get("tags", [])
            file_path = self._get_knowledge_path(knowledge_id, tags)
            if file_path.exists():
                file_path.unlink()
        
        result = super().delete(knowledge_id)
        if result:
            self._save()  # 更新标签索引
        return result
