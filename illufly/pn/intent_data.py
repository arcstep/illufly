import os
import json
import numpy as np
import torch

from typing import List, Dict, Any, Optional
from torch.utils.data import Dataset
from tqdm import tqdm

from ..community import OpenAIEmbeddings

class IntentDataset(Dataset):
    """意图数据集类"""
    
    def __init__(
        self, 
        data: List[Dict[str, Any]], 
        intent_types: List[str],
        embedding_model: Optional[OpenAIEmbeddings] = None,
        max_history_len: int = 10,
        imitator: Optional[str] = None
    ):
        """
        初始化数据集
        
        Args:
            data: 训练数据列表，每条包含query和intent
            intent_types: 支持的意图类型列表
            embedding_model: 嵌入模型，如果为None则创建新实例
            max_history_len: 最大历史长度
            imitator: 嵌入模型imitator
        """
        self.data = data
        self.intent_types = intent_types
        self.intent_to_id = {intent: i for i, intent in enumerate(intent_types)}
        self.max_history_len = max_history_len

        # 初始化或加载嵌入模型
        self.embedding_model = embedding_model or OpenAIEmbeddings(
            model="text-embedding-ada-002",
            imitator=imitator or "OPENAI",
            dim=1536
        )
        
        # 设置设备
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    def __len__(self):
        return len(self.data)
    
    def __getitem__(self, idx):
        item = self.data[idx]
        query = item["query"]
        intent = item["intent"]
        
        # 获取嵌入向量
        embeddings = self.embedding_model.sync_embed_texts([query])
        embedding = torch.tensor(embeddings[0].vector, dtype=torch.float32)
        if embedding is None:
            raise ValueError(f"未找到查询的嵌入向量: {query}")
        
        # 获取意图ID
        intent_id = self.intent_to_id.get(intent)
        if intent_id is None:
            raise ValueError(f"未知意图类型: {intent}")
        
        # 处理历史（如果有）
        history = item.get("history", [])
        # 转换历史意图为ID
        history_ids = []
        for h_intent in history[-self.max_history_len:]:
            if h_intent in self.intent_to_id:
                history_ids.append(self.intent_to_id[h_intent])
            else:
                # 未知意图使用特殊ID
                history_ids.append(len(self.intent_types))
        
        # 填充历史
        padded_history = [0] * self.max_history_len  # 0 as padding
        history_len = min(len(history_ids), self.max_history_len)
        padded_history[-history_len:] = history_ids[-history_len:]
        
        return {
            "query_embed": torch.tensor(embedding, dtype=torch.float32),
            "intent_id": torch.tensor(intent_id, dtype=torch.long),
            "history": torch.tensor(padded_history, dtype=torch.long),
            "history_len": torch.tensor(history_len, dtype=torch.long),
            "metadata": {
                "query": query,
                "intent": intent
            }
        }
