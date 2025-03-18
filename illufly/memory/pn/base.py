from typing import List, Dict, Tuple, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import json
import random
import logging
import asyncio
import os
import re
from collections import Counter
from torch.utils.data import TensorDataset, DataLoader, WeightedRandomSampler
import threading
from functools import partial
import contextlib
from threading import local as ThreadLocal

# 导入您封装的向量模型
from ...community.openai import OpenAIEmbeddings, ChatOpenAI
from .monitor import FeatureMonitor
from .llm import LLMInterface

# 配置日志
logger = logging.getLogger(__name__)

@dataclass
class ActionSpace:
    """动作空间定义"""
    DIRECT_DIALOGUE: int = 0      # 直接对话
    QUERY_KNOWLEDGE: int = 1      # 查询知识库  
    QUERY_DATABASE: int = 2       # 查询数据库

@dataclass
class PolicyPrediction:
    """策略网络预测结果"""
    action_type: int              # 动作类型
    confidence: float             # 置信度
    action_params: Dict           # 动作参数 (例如查询语句)
    probabilities: List[float]    # 所有动作的概率分布

class QueryGenerator(nn.Module):
    """查询生成器"""
    def __init__(self, input_dim: int, hidden_dim: int):
        super().__init__()
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim)
        
    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = self.fc2(x)
        return x

class FeatureProcessor(nn.Module):
    """支持OpenAI 1536维的特征处理器"""
    def __init__(self, input_dim: int = 1536, proj_dim: int = 768, num_heads: int = 8):
        super().__init__()
        # 维度适配层（OpenAI 1536 → 768）
        self.projector = nn.Sequential(
            nn.Linear(input_dim, proj_dim),
            nn.LayerNorm(proj_dim),
            nn.GELU(),
            nn.Dropout(0.1)
        )
        # 自注意力层（显式处理维度）
        self.attention = nn.MultiheadAttention(
            embed_dim=proj_dim,
            num_heads=num_heads,
            batch_first=True  # 关键修复点
        )
        # 后处理层
        self.post_norm = nn.LayerNorm(proj_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        输入形状: (batch_size, 1536)
        输出形状: (batch_size, 768)
        """
        # 添加输入维度校验
        if x.dim() != 2:
            raise ValueError(f"输入应为二维张量，实际维度: {x.dim()}")
        
        # 维度投影 (batch_size, 1536) → (batch_size, 768)
        x_proj = self.projector(x)
        
        # 添加序列维度 (batch_size, 1, 768)
        x_seq = x_proj.unsqueeze(1)
        
        # 自注意力计算（显式传递key和value）
        attn_out, _ = self.attention(
            query=x_seq,
            key=x_seq,
            value=x_seq
        )
        
        # 残差连接 + 层归一化
        output = self.post_norm(x_seq + attn_out)
        
        # 移除序列维度 (batch_size, 768)
        return output.squeeze(1)

class PolicyNetwork(nn.Module):
    """统一增强版策略网络"""
    _thread_local = ThreadLocal()  # 使用线程本地存储替代锁

    def __init__(
        self, 
        embeddings: OpenAIEmbeddings = None,
        actions: List[str] = None,
        confidence_threshold: float = 0.7,
        model_path: str = None,
        imitator: str = None,
        proj_dim: int = 768,  # 新增投影维度参数
        **kwargs
    ):
        super().__init__()
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        # 初始化向量模型
        self.embeddings = embeddings or OpenAIEmbeddings(
            model="text-embedding-ada-002",
            imitator="OPENAI",
            dim=1536
        )
        self.hidden_dim = self.embeddings.dim
        
        # 动作空间定义与管理
        self.action_names = actions or ["直接对话", "查询知识库", "查询数据库"]
        self.action_space_size = len(self.action_names)
        
        # 统一使用英文键名
        self.action_key_map = {
            "直接对话": "direct",
            "查询知识库": "knowledge",
            "查询数据库": "database"
        }
        
        # 置信度阈值
        self.confidence_threshold = confidence_threshold
        
        # 延迟初始化关键组件
        self.decision_head = None
        self.query_generators = None
        
        # 统一路径处理
        self.model_dir = os.path.dirname(model_path) if model_path else "./models"
        os.makedirs(self.model_dir, exist_ok=True)
        
        # 自动查找最新模型
        latest_model = self._find_latest_model(self.model_dir)
        if latest_model:
            logger.info(f"加载最新模型: {latest_model}")
            self._load_pretrained(latest_model)
        else:
            self._rebuild_network()
        
        # 将优化器初始化移到网络构建之后
        self._init_optimizer()  # 移动到这里
        
        # 添加动作注册表（新增）
        self._action_registry = {
            "direct": "直接对话",
            "knowledge": "查询知识库", 
            "database": "查询数据库",
            "external_api": "调用外部API"  # 新增标准动作
        }
        
        # 特征处理模块（原Enhanced部分）
        self.feature_processor = FeatureProcessor(input_dim=1536, proj_dim=768, num_heads=8)
        
        # 修改决策头输入维度
        self.decision_head = nn.Sequential(
            nn.Linear(768, 256),  # 输入维度改为768（特征处理器输出维度）
            nn.ReLU(),
            nn.Linear(256, self.action_space_size)
        )
        
        # 质量预测头同步修改
        self.quality_head = nn.Linear(768, 1)  # 输入维度改为768
        
        self.auto_save = True  # 新增自动保存开关
        self.keep_last_n = 3   # 保留最近3个模型
        
    def _init_optimizer(self, train_data: List[Dict] = None):
        """动态初始化损失函数"""
        # 自动计算类别权重
        if train_data is not None:
            class_counts = Counter([d['action_type'] for d in train_data])
            weights = 1.0 / torch.tensor(
                [class_counts[i] for i in sorted(class_counts)],
                dtype=torch.float32
            )
            weights = weights / weights.sum()  # 归一化
        else:
            # 默认等权重（兼容模式）
            weights = torch.ones(self.action_space_size)
        
        self.criterion = nn.CrossEntropyLoss(
            weight=weights.to(self.device)
        )
        
        # 原有优化器初始化
        self.optimizer = torch.optim.AdamW(
            self.parameters(),
            lr=1e-5,
            weight_decay=0.01
        )
        
        # 添加梯度裁剪
        if self.optimizer.param_groups:  # 新增有效性检查
            torch.nn.utils.clip_grad_norm_(
                self.parameters(),
                max_norm=2.0
            )
        
        logger.debug("优化器初始化完成，参数数量: %d", len(list(self.parameters())))
        
    def _load_pretrained(self, path: str):
        checkpoint = torch.load(path)
        
        if "version" not in checkpoint:  # 旧版模型
            logger.warning("检测到旧版模型，启用兼容模式")
            self._load_legacy_model(checkpoint)
        else:
            self.load_state_dict(checkpoint["state_dict"])
        
        # 加载后重新初始化关键组件
        self._init_optimizer()  # 确保criterion被创建
        
    def _find_latest_model(self, model_dir: str) -> Optional[str]:
        """改进的最新模型查找方法"""
        model_files = []
        for f in os.listdir(model_dir):
            if f.startswith('policy_net_') and f.endswith('.pt'):
                try:
                    # 从文件名解析时间戳
                    timestamp_str = re.search(r'policy_network_(\d{8}_\d{6})', f).group(1)
                    timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                    model_files.append((f, timestamp))
                except:
                    continue
        
        if not model_files:
            return None
        
        # 按时间戳降序排序
        sorted_models = sorted(model_files, key=lambda x: x[1], reverse=True)
        return os.path.join(model_dir, sorted_models[0][0])
        
    def _load_from_file(self, path: str) -> bool:
        try:
            save_dict = torch.load(path)
            # 添加版本检查
            if "version" not in save_dict or save_dict["version"] != "2.4":
                logger.warning("检测到旧版模型格式，建议进行迁移")
            
            # 优先使用模型自带的动作列表
            if 'action_names' in save_dict:
                self.action_names = save_dict['action_names']
                self.action_space_size = len(self.action_names)
                logger.info(f"从模型加载动作空间: {self.action_names}")
            
            # 同步键名映射
            self.action_key_map = save_dict.get('action_key_map', self.action_key_map)
            
            # 动态重建网络结构
            self._rebuild_network()
            
            # 键名转换
            new_state_dict = {}
            for k, v in save_dict['model_state'].items():
                new_k = re.sub(
                    r'query_generators.(\W+)',
                    lambda m: f"query_generators.{self.action_key_map.get(m.group(1), m.group(1))}",
                    k
                )
                new_state_dict[new_k] = v
            
            # 严格模式加载
            self.load_state_dict(new_state_dict, strict=True)
            return True
        except Exception as e:
            logger.error(f"模型加载失败: {str(e)}")
            return False

    def _rebuild_network(self):
        """根据当前动作空间重建网络组件"""
        # 重建决策头
        self.decision_head = nn.Sequential(
            nn.Linear(self.hidden_dim, self.action_space_size)
        )
        
        # 重建查询生成器
        self.query_generators = nn.ModuleDict()
        for action in self.action_names:
            action_key = self.action_key_map.get(action, action.lower().replace(" ", "_"))
            self.query_generators[action_key] = QueryGenerator(self.hidden_dim, self.hidden_dim)

    def encode_text(self, text: str) -> torch.Tensor:
        """修正后的编码方法"""
        embedding_texts = self.embeddings.sync_embed_texts([text])        
        return torch.tensor(embedding_texts[0].vector).unsqueeze(0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """修改后的前向传播"""
        projected = self.feature_processor(x)
        # 添加维度校验
        if projected.dim() == 3:
            projected = projected.squeeze(1)
        action_logits = self.decision_head(projected)
        return {
            "action_logits": action_logits,
            "action_probs": F.softmax(action_logits, dim=1)  # 注意dim=1
        }
    
    async def predict(self, query: str) -> PolicyPrediction:
        """预测用户查询的处理策略"""
        self.eval()
        
        # 编码查询
        encoded_query = self.encode_text(query)
        
        # 获取模型输出
        with torch.no_grad():
            outputs = self.forward(encoded_query)
        
        # 获取动作概率
        logits = outputs["action_logits"]
        action_probs = outputs["action_probs"].cpu().numpy()
        if action_probs.ndim == 2:  # 处理批量数据
            action_probs = action_probs[0]
        
        # 选择最高概率动作
        action_type = int(np.argmax(action_probs))
        confidence = float(action_probs[action_type])
        
        # 准备动作参数
        action_params = {}
        if action_type == ActionSpace.QUERY_KNOWLEDGE:
            # 生成知识库查询语句
            action_params["query"] = query
        elif action_type == ActionSpace.QUERY_DATABASE:
            # 生成数据库查询语句
            action_params["sql"] = f"SELECT * FROM relevant_table WHERE content LIKE '%{query}%'"
            
        return PolicyPrediction(
            action_type=action_type,
            confidence=confidence,
            action_params=action_params,
            probabilities=action_probs.tolist()
        )
        
    async def save(self, model_dir: str = "./tests/pn/models"):
        """带时间戳的模型保存方法"""
        # 确保目录存在
        os.makedirs(model_dir, exist_ok=True)
        
        # 生成带时间戳的文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_path = os.path.join(model_dir, f"policy_net_{timestamp}.pt")
        
        # 异步保存（如果需要处理大模型）
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: torch.save(self.state_dict(), model_path)
        )
        
        logger.info(f"模型已保存至: {model_path}")
        
        # 清理旧模型
        if self.keep_last_n > 0:
            models = sorted(Path(model_dir).glob("policy_net_*.pt"))
            for old_model in models[:-self.keep_last_n]:
                old_model.unlink()
        
        return model_path
    
    @classmethod
    def load(cls, path: str, embeddings: OpenAIEmbeddings):
        """加载时处理键名兼容"""
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        save_dict = torch.load(path, map_location=device)
        
        # 键名转换逻辑
        state_dict = save_dict["model_state"]
        new_state_dict = {}
        for k, v in state_dict.items():
            new_k = k.replace("查询知识库", "knowledge").replace("查询数据库", "database")
            new_state_dict[new_k] = v
        
        # 初始化网络
        net = cls(
            embeddings=embeddings,
            confidence_threshold=save_dict.get("confidence_threshold", 0.7)
        )
        net.load_state_dict(new_state_dict)
        
        return net

    async def train_network(
        self,
        train_data: List[Dict],
        val_data: Optional[List[Dict]] = None,
        epochs: int = 20,
        batch_size: int = 64,
        lr: float = 3e-5,
        patience: int = 5,
        val_ratio: float = 0.2,
        batch_evolution: List[int] = None
    ):
        # 在优化器定义后添加调度器初始化
        optimizer = torch.optim.AdamW(self.parameters(), lr=lr)
        
        # 新增学习率调度器定义
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer,
            mode='max',  # 根据验证准确率调整
            factor=0.5,
            patience=2,
            verbose=True
        )
        
        # 修复批次演进策略初始化
        if batch_evolution is None:
            # 确保默认值包含当前batch_size
            batch_evolution = [
                max(8, batch_size//4), 
                max(16, batch_size//2), 
                batch_size
            ]
        else:
            # 确保用户传入的列表包含最终目标batch_size
            if batch_size not in batch_evolution:
                batch_evolution.append(batch_size)
        
        # 添加有效性检查
        if not isinstance(batch_evolution, list) or len(batch_evolution) < 1:
            raise ValueError("batch_evolution 必须是包含至少一个元素的列表")

        # 初始化最佳验证准确率
        best_val_acc = 0.0
        no_improve = 0
        
        # 在训练循环前初始化 total_loss
        total_loss = 0.0  # 新增初始化

        monitor = FeatureMonitor()
        
        # 修改训练循环
        for epoch in range(epochs):
            total_loss = 0.0  # 每个epoch重置
            current_stage = 0
            effective_batch_size = batch_evolution[current_stage]
            
            # 修改训练循环中的阶段切换逻辑
            for batch in self._data_loader(train_data, effective_batch_size):
                loss = await self._train_batch(batch)
                total_loss += loss * len(batch)  # 加权计算
                
                # 修复特征记录逻辑（统一使用动态生成）
                with torch.no_grad():
                    # 动态生成向量（与_train_batch逻辑一致）
                    queries = [item["user_query"] for item in batch]
                    embedding_texts = await self.embeddings.embed_texts(queries)
                    vectors = [emb.vector for emb in embedding_texts]
                    
                    features = self.feature_processor(
                        torch.tensor(vectors)  # 使用动态生成的向量
                    ).cpu().numpy()
                for feat, label in zip(features, [x['action_type'] for x in batch]):
                    monitor.log_features(feat, label)
            
            # 计算平均损失时使用总样本数
            avg_loss = total_loss / len(train_data)
            logger.info(f"第 {epoch+1} 轮平均损失: {avg_loss:.4f}")
            
            # 验证阶段
            if val_data:  # 新增有效性检查
                val_acc = await self.validate(val_data)
                # 早停判断（修复参数传递）
                if val_acc > best_val_acc:
                    best_val_acc = val_acc
                    no_improve = 0
                    await self.save()  # 添加await
                else:
                    no_improve += 1
                    if no_improve >= patience:
                        logger.info("早停触发，停止训练")
                        break
            else:
                logger.warning("未提供验证集，跳过验证和早停机制")
            
            # 学习率调度
            scheduler.step(avg_loss)
            
        # 分析特征空间
        monitor.visualize()
        
        # 在训练循环后添加清理操作
        try:
            # 确保所有异步操作完成
            await asyncio.gather(*asyncio.all_tasks())
            
            # 显式关闭文件句柄
            if 'monitor' in locals():
                monitor.close()
            
            # 强制刷新日志
            logging.getLogger().handlers[0].flush()
            
        except Exception as e:
            logger.error(f"清理异常: {str(e)}")
        
        # 添加最终完成标记
        logger.info("训练流程完整结束")
        return {
            "best_val_acc": best_val_acc,
            "final_val_acc": best_val_acc,
            "training_loss": avg_loss,  # 使用最后计算的avg_loss
            "feature_quality": monitor.calculate_separability()
        }

    def _stratified_split(self, data: List[Dict], ratio: float) -> Tuple[List, List]:
        """分层抽样分割方法"""
        from sklearn.model_selection import train_test_split
        
        labels = [d['action_type'] for d in data]
        train_idx, val_idx = train_test_split(
            range(len(data)), 
            test_size=ratio, 
            stratify=labels,
            random_state=42
        )
        return [data[i] for i in train_idx], [data[i] for i in val_idx]

    def _data_loader(self, data: List, batch_size: int):
        """改进后的数据加载器"""
        # 添加随机打乱
        indices = np.random.permutation(len(data))
        shuffled_data = [data[i] for i in indices]
        
        # 添加分层采样
        class_counts = Counter([d['action_type'] for d in shuffled_data])
        weights = [1.0 / class_counts[d['action_type']] for d in shuffled_data]
        sampler = WeightedRandomSampler(weights, len(shuffled_data), replacement=True)
        
        # 使用PyTorch DataLoader
        dataset = TensorDataset(
            torch.arange(len(shuffled_data)),  # 伪数据，实际使用特征向量
            torch.tensor([d['action_type'] for d in shuffled_data])
        )
        
        return DataLoader(
            dataset,
            batch_size=batch_size,
            sampler=sampler,
            collate_fn=lambda batch: [shuffled_data[i] for i, _ in batch]
        )

    async def _train_batch(self, batch: List[Dict]) -> float:
        """添加防御性检查"""
        if not hasattr(self, 'criterion'):
            raise RuntimeError("损失函数未初始化，请检查_init_optimizer实现")
        
        # 修复混合精度训练的条件判断
        if torch.cuda.is_available():
            scaler = torch.cuda.amp.GradScaler()
            with torch.cuda.amp.autocast():
                # 准备数据
                queries = [item["user_query"] for item in batch]
                action_types = torch.tensor([item["action_type"] for item in batch])
                
                # 动态生成向量（修复缺失vector字段问题）
                try:
                    embedding_texts = await self.embeddings.embed_texts(queries)
                    vectors = [emb.vector for emb in embedding_texts]
                    encoded_queries = torch.tensor(vectors).to(self.device)  # 添加设备转移
                except Exception as e:
                    logger.error(f"嵌入获取失败: {str(e)}")
                    return 0.0
                
                # 添加维度校验
                if encoded_queries.dim() == 1:
                    encoded_queries = encoded_queries.unsqueeze(0)
                elif encoded_queries.dim() > 2:
                    encoded_queries = encoded_queries.squeeze(1)
                
                # 添加类型转换
                encoded_queries = encoded_queries.float()  # 确保浮点类型
                
                # 前向传播
                outputs = self.forward(encoded_queries)
                
                # 多任务损失计算
                action_loss = self.criterion(outputs["action_logits"], action_types)
                
                # 修正维度匹配
                quality_targets = torch.tensor(
                    [item.get('quality', 0.8) for item in batch],
                    dtype=torch.float32,
                    device=self.device
                ).unsqueeze(1)  # 添加维度 [batch_size, 1]
                
                quality_loss = F.mse_loss(
                    outputs["quality_score"], 
                    quality_targets
                )
                
                total_loss = action_loss + 0.3 * quality_loss
                
        else:
            # 显式定义CPU模式下的total_loss
            self.optimizer.zero_grad()
            
            # 准备数据
            queries = [item["user_query"] for item in batch]
            action_types = torch.tensor([item["action_type"] for item in batch])
            
            # 动态生成向量
            embedding_texts = await self.embeddings.embed_texts(queries)
            vectors = [emb.vector for emb in embedding_texts]
            encoded_queries = torch.tensor(vectors).float()
            
            # 前向传播
            outputs = self.forward(encoded_queries)
            
            # 计算损失
            action_loss = self.criterion(outputs["action_logits"], action_types)
            total_loss = action_loss
            
            # 反向传播
            total_loss.backward()
            self.optimizer.step()
        
        return total_loss.item()

    async def validate(self, val_data: List[Dict]) -> float:
        """验证集评估"""
        correct = 0
        for item in val_data:
            pred = await self.predict(item["user_query"])
            if pred.action_type == item["action_type"]:
                correct += 1
        return correct / len(val_data)

    def __del__(self):
        """对象销毁时清理事件循环"""
        if hasattr(self._thread_local, "loop"):
            self._thread_local.loop.close()
            del self._thread_local.loop
