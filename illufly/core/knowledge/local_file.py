from pathlib import Path
import json
from typing import Dict, List, Union
from .base import BaseKnowledge
from ..document import Document
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
        """从目录加载所有知识条目"""
        if not (self.directory / "knowledge.json").exists():
            return
            
        with open(self.directory / "knowledge.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            self.store = data.get("store", {})
            self.tag_index = {
                tag: set(ids) for tag, ids in data.get("tag_index", {}).items()
            }
    
    def _save(self) -> None:
        """保存所有知识条目到目录"""
        data = {
            "store": self.store,
            "tag_index": {
                tag: list(ids) for tag, ids in self.tag_index.items()
            }
        }
        with open(self.directory / "knowledge.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def add(self, text: str, tags: List[str]=None, summary: str="", source: str=None) -> str:
        """重写add方法，添加后自动保存"""
        knowledge_id = super().add(text, tags, summary, source)
        self._save()
        return knowledge_id
    
    def update(
        self,
        knowledge_id: str,
        text: str=None,
        tags: List[str]=None,
        summary: str=None,
        source: str=None
    ) -> bool:
        """重写update方法，更新后自动保存"""
        result = super().update(knowledge_id, text, tags, summary, source)
        if result:
            self._save()
        return result
    
    def delete(self, knowledge_id: str) -> bool:
        """重写delete方法，删除后自动保存"""
        result = super().delete(knowledge_id)
        if result:
            self._save()
        return result