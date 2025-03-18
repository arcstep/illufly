import os
import json
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import logging
import traceback

from typing import List, Dict, Any, Optional, Tuple, Union
from torch.utils.data import Dataset, DataLoader
from datetime import datetime
from tqdm import tqdm
from collections import defaultdict

from ..community import OpenAIEmbeddings

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TextEncoder(nn.Module):
    """文本编码器，从原始文本到向量表示"""
    
    def __init__(
        self, 
        embedding_model: Optional[OpenAIEmbeddings] = None,
        use_attention: bool = True,
        proj_dim: int = 768,
        attention_heads: int = 8,
        imitator: Optional[str] = None
    ):
        super().__init__()
        # 初始化向量模型
        self.embedding_model = embedding_model or OpenAIEmbeddings(
            model="text-embedding-ada-002",
            imitator=imitator or "OPENAI",
            dim=1536
        )
        
        self.input_dim = self.embedding_model.dim
        self.use_attention = use_attention
        self.proj_dim = proj_dim
        
        # 投影层 - 将1536维的向量映射到指定维度
        self.projector = nn.Sequential(
            nn.Linear(self.input_dim, proj_dim),
            nn.LayerNorm(proj_dim),
            nn.GELU(),
            nn.Dropout(0.1)
        )
        
        # 可选的自注意力层
        if use_attention:
            self.attention = nn.MultiheadAttention(
                embed_dim=proj_dim,
                num_heads=attention_heads,
                batch_first=True
            )
            self.post_norm = nn.LayerNorm(proj_dim)
        
    def encode_text(self, text: str) -> torch.Tensor:
        """将原始文本编码为向量"""
        embeddings = self.embedding_model.sync_embed_texts([text])
        embedding_vector = torch.tensor(embeddings[0].vector, dtype=torch.float32)
        return embedding_vector.unsqueeze(0)  # 添加批次维度
    
    def forward(self, x: Union[str, torch.Tensor]) -> torch.Tensor:
        """
        处理输入文本或向量
        
        Args:
            x: 文本字符串或者已经编码的向量 (batch_size, input_dim)
            
        Returns:
            处理后的向量 (batch_size, proj_dim)
        """
        # 如果输入是文本，先编码
        if isinstance(x, str):
            x = self.encode_text(x)
        
        # 投影到指定维度
        x_proj = self.projector(x)
        
        # 如果启用注意力机制
        if self.use_attention:
            # 添加序列维度 (batch_size, 1, proj_dim)
            x_seq = x_proj.unsqueeze(1)
            
            # 自注意力计算
            attn_out, _ = self.attention(
                query=x_seq,
                key=x_seq,
                value=x_seq
            )
            
            # 残差连接 + 层归一化
            output = self.post_norm(x_seq + attn_out)
            
            # 移除序列维度 (batch_size, proj_dim)
            return output.squeeze(1)
        else:
            # 不使用注意力，直接返回投影结果
            return x_proj

class HierarchicalAttention(nn.Module):
    """层级注意力机制，用于捕捉意图的大类和小类关系"""
    
    def __init__(
        self, 
        embed_dim: int = 768, 
        num_heads: int = 8,
        dropout: float = 0.1,
        use_hierarchical: bool = True
    ):
        super().__init__()
        self.embed_dim = embed_dim
        self.use_hierarchical = use_hierarchical
        
        # 主注意力层
        self.primary_attention = nn.MultiheadAttention(
            embed_dim=embed_dim,
            num_heads=num_heads,
            batch_first=True,
            dropout=dropout
        )
        
        # 如果使用层级结构，添加二级注意力
        if use_hierarchical:
            # 二级注意力层，用于捕捉更细粒度的关系
            self.secondary_attention = nn.MultiheadAttention(
                embed_dim=embed_dim,
                num_heads=num_heads // 2,  # 降低头数，关注更细的模式
                batch_first=True,
                dropout=dropout
            )
            
            # 融合层，结合两级注意力结果
            self.fusion = nn.Sequential(
                nn.Linear(embed_dim * 2, embed_dim),
                nn.LayerNorm(embed_dim),
                nn.GELU()
            )
        
        # 层归一化
        self.norm1 = nn.LayerNorm(embed_dim)
        self.norm2 = nn.LayerNorm(embed_dim)
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        应用层级注意力机制
        
        Args:
            x: 输入张量 (batch_size, seq_len, embed_dim)
            
        Returns:
            处理后的张量 (batch_size, embed_dim)
        """
        # 对单个向量，添加序列维度
        if x.dim() == 2:
            x = x.unsqueeze(1)
            
        # 主注意力计算
        attn_out1, _ = self.primary_attention(x, x, x)
        x1 = self.norm1(x + attn_out1)
        
        if self.use_hierarchical:
            # 二级注意力计算
            attn_out2, _ = self.secondary_attention(x1, x1, x1)
            x2 = self.norm2(x1 + attn_out2)
            
            # 提取序列的表示（取平均）
            x1_mean = x1.mean(dim=1)
            x2_mean = x2.mean(dim=1)
            
            # 融合两级表示
            combined = torch.cat([x1_mean, x2_mean], dim=1)
            output = self.fusion(combined)
        else:
            # 不使用层级结构，直接取平均
            output = x1.mean(dim=1)
            
        return output

class HistoryEncoder(nn.Module):
    """用户历史动作编码器，处理时间序列特征"""
    
    def __init__(
        self, 
        action_space_size: int,
        use_gru: bool = True,
        embed_dim: int = 128, 
        hidden_dim: int = 256,
        num_layers: int = 2,
        dropout: float = 0.1
    ):
        super().__init__()
        self.use_gru = use_gru
        
        # 动作嵌入层
        self.action_embedding = nn.Embedding(action_space_size, embed_dim)
        
        if use_gru:
            # GRU层处理序列
            self.gru = nn.GRU(
                input_size=embed_dim,
                hidden_size=hidden_dim,
                num_layers=num_layers,
                batch_first=True,
                dropout=dropout if num_layers > 1 else 0
            )
        else:
            # 简单的线性投影，用于基线模型
            self.linear_proj = nn.Sequential(
                nn.Linear(embed_dim, hidden_dim),
                nn.LayerNorm(hidden_dim),
                nn.ReLU()
            )
        
        # 输出层
        self.output_size = hidden_dim
        
    def forward(self, action_history: torch.Tensor, history_lengths: torch.Tensor) -> torch.Tensor:
        """
        处理用户历史动作序列
        
        Args:
            action_history: 形状为 (batch_size, max_seq_len) 的用户动作ID序列
            history_lengths: 形状为 (batch_size,) 的序列实际长度
        
        Returns:
            形状为 (batch_size, hidden_dim) 的历史特征表示
        """
        # 动作ID转为嵌入向量
        embedded = self.action_embedding(action_history)
        
        if self.use_gru:
            # 打包填充序列
            packed = nn.utils.rnn.pack_padded_sequence(
                embedded, 
                history_lengths.cpu(), 
                batch_first=True, 
                enforce_sorted=False
            )
            
            # GRU处理
            _, last_hidden = self.gru(packed)
            
            # 取最后一层隐状态作为输出
            return last_hidden[-1]
        else:
            # 基线模型：简单地平均所有历史嵌入
            # 创建掩码来忽略填充位置
            mask = torch.arange(embedded.size(1)).unsqueeze(0) < history_lengths.unsqueeze(1)
            mask = mask.to(embedded.device).unsqueeze(2).float()
            
            # 应用掩码并计算平均值
            masked_embedded = embedded * mask
            sum_embedded = masked_embedded.sum(dim=1)
            
            # 避免除以零
            avg_denominator = torch.clamp(history_lengths, min=1).unsqueeze(1).float().to(embedded.device)
            avg_embedded = sum_embedded / avg_denominator
            
            # 线性投影
            return self.linear_proj(avg_embedded)

class ModuleSelector(nn.Module):
    """模块选择器，实现模块的开关功能"""
    
    def __init__(
        self, 
        primary_module: nn.Module,
        fallback_module: Optional[nn.Module] = None,
        enabled: bool = True
    ):
        super().__init__()
        self.primary = primary_module
        self.fallback = fallback_module
        self.enabled = enabled
        
    def forward(self, *args, **kwargs):
        """根据启用状态选择不同的模块"""
        if self.enabled and self.primary is not None:
            return self.primary(*args, **kwargs)
        elif self.fallback is not None:
            return self.fallback(*args, **kwargs)
        else:
            # 如果两个模块都不可用，抛出错误
            raise ValueError("没有可用的模块(primary已禁用且fallback为None)")
    
    def toggle(self, enabled: bool = None):
        """切换模块启用状态"""
        if enabled is not None:
            self.enabled = enabled
        else:
            self.enabled = not self.enabled
        return self.enabled

class EnhancedIntentPolicyNetwork(nn.Module):
    """
    高度模块化的意图策略网络，支持各层的开关控制
    """
    def __init__(
        self, 
        intent_types: List[str],
        # 模块开关配置
        use_text_attention: bool = True,      # 是否使用文本自注意力
        use_hierarchical: bool = True,        # 是否使用层级注意力
        use_history_gru: bool = True,         # 是否使用GRU处理历史
        use_fusion: bool = True,              # 是否使用复杂融合层
        use_quality_head: bool = True,        # 是否使用质量评估头
        # 模型维度配置
        embed_dim: int = 768,                 # 文本嵌入维度
        history_dim: int = 256,               # 历史特征维度
        fusion_dim: int = 512,                # 融合层维度
        # 其他配置
        embeddings: Optional[OpenAIEmbeddings] = None,
        max_history_len: int = 10,
        confidence_threshold: float = 0.7,
        model_path: Optional[str] = None,
        imitator: Optional[str] = None,
        **kwargs
    ):
        super().__init__()
        # 设备配置
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # 意图空间定义
        self.intent_types = intent_types
        self.intent_space_size = len(self.intent_types)
        self.intent_to_id = {intent: i for i, intent in enumerate(self.intent_types)}
        self.id_to_intent = {i: intent for i, intent in enumerate(self.intent_types)}
        
        # 保存模块配置
        self.config = {
            "use_text_attention": use_text_attention,
            "use_hierarchical": use_hierarchical,
            "use_history_gru": use_history_gru,
            "use_fusion": use_fusion,
            "use_quality_head": use_quality_head,
            "embed_dim": embed_dim,
            "history_dim": history_dim,
            "fusion_dim": fusion_dim,
            "max_history_len": max_history_len
        }
        
        # 初始化嵌入模型
        self.embedding_model = embeddings or OpenAIEmbeddings(
            model="text-embedding-ada-002",
            imitator=imitator or "OPENAI",
            dim=1536
        )
        
        # 历史设置
        self.max_history_len = max_history_len
        
        # 置信度阈值
        self.confidence_threshold = confidence_threshold
        
        # 文本编码器
        self.text_encoder = TextEncoder(
            embedding_model=self.embedding_model,
            use_attention=use_text_attention,
            proj_dim=embed_dim
        )
        
        # 层级注意力模块
        primary_hierarchical = HierarchicalAttention(
            embed_dim=embed_dim,
            use_hierarchical=True
        )
        fallback_hierarchical = nn.Identity()  # 不使用层级时的替代模块
        
        self.hierarchical_attention = ModuleSelector(
            primary_module=primary_hierarchical,
            fallback_module=fallback_hierarchical,
            enabled=use_hierarchical
        )
        
        # 历史编码器
        self.history_encoder = HistoryEncoder(
            action_space_size=self.intent_space_size + 1,  # +1 用于padding
            use_gru=use_history_gru,
            embed_dim=128,
            hidden_dim=history_dim
        )
        
        # 融合层 - 高级版本
        advanced_fusion = nn.Sequential(
            nn.Linear(embed_dim + history_dim, fusion_dim),
            nn.LayerNorm(fusion_dim),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(fusion_dim, fusion_dim),
            nn.LayerNorm(fusion_dim),
            nn.GELU()
        )
        
        # 融合层 - 基础版本
        basic_fusion = nn.Sequential(
            nn.Linear(embed_dim + history_dim, fusion_dim),
            nn.ReLU()
        )
        
        self.fusion_layer = ModuleSelector(
            primary_module=advanced_fusion,
            fallback_module=basic_fusion,
            enabled=use_fusion
        )
        
        # 决策头
        self.decision_head = nn.Sequential(
            nn.Linear(fusion_dim, 256),
            nn.ReLU(),
            nn.Linear(256, self.intent_space_size)
        )
        
        # 质量评估头
        self.quality_head = ModuleSelector(
            primary_module=nn.Linear(fusion_dim, 1),
            fallback_module=None,  # 不使用质量头时，预测时会使用固定值
            enabled=use_quality_head
        )
        
        # 优化器设置
        self._init_optimizer()
        
        # 模型路径管理
        self.model_dir = os.path.dirname(model_path) if model_path else "./models"
        os.makedirs(self.model_dir, exist_ok=True)
        
        # 加载已有模型
        if model_path and os.path.exists(model_path):
            self.load_model(model_path)
        elif model_path:
            latest_model = self._find_latest_model()
            if latest_model:
                logger.info(f"加载最新模型: {latest_model}")
                self.load_model(latest_model)
        
        # 移动到设备
        self.to(self.device)
        
        # 模型版本和保存设置
        self.model_version = datetime.now().strftime("%Y%m%d%H%M")
        self.auto_save = True
        self.keep_last_n = 3
    
    def _init_optimizer(self):
        """初始化优化器"""
        self.optimizer = optim.AdamW(self.parameters(), lr=1e-4, weight_decay=1e-5)
        self.scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            self.optimizer, 
            mode='min', 
            factor=0.5, 
            patience=5,
            verbose=True
        )
    
    def _find_latest_model(self) -> Optional[str]:
        """查找最新模型文件"""
        models = [f for f in os.listdir(self.model_dir) if f.startswith("intent_policy_") and f.endswith(".pt")]
        if not models:
            return None
        
        models.sort(reverse=True)  # 根据文件名排序（包含日期时间）
        return os.path.join(self.model_dir, models[0])
    
    def toggle_module(self, module_name: str, enabled: Optional[bool] = None) -> bool:
        """
        切换指定模块的启用状态
        
        Args:
            module_name: 模块名称
            enabled: 是否启用，None表示切换当前状态
            
        Returns:
            模块启用状态
        """
        if module_name == "text_attention":
            # 注意: TextEncoder不是ModuleSelector，需要重新创建
            current = self.text_encoder.use_attention
            new_state = not current if enabled is None else enabled
            if current != new_state:
                self.text_encoder = TextEncoder(
                    embedding_model=self.embedding_model,
                    use_attention=new_state,
                    proj_dim=self.config["embed_dim"]
                ).to(self.device)
            self.config["use_text_attention"] = new_state
            return new_state
        elif module_name == "hierarchical":
            result = self.hierarchical_attention.toggle(enabled)
            self.config["use_hierarchical"] = result
            return result
        elif module_name == "history_gru":
            # History也需要重新创建
            current = self.history_encoder.use_gru
            new_state = not current if enabled is None else enabled
            if current != new_state:
                self.history_encoder = HistoryEncoder(
                    action_space_size=self.intent_space_size + 1,
                    use_gru=new_state,
                    hidden_dim=self.config["history_dim"]
                ).to(self.device)
            self.config["use_history_gru"] = new_state
            return new_state
        elif module_name == "fusion":
            result = self.fusion_layer.toggle(enabled)
            self.config["use_fusion"] = result
            return result
        elif module_name == "quality_head":
            result = self.quality_head.toggle(enabled)
            self.config["use_quality_head"] = result
            return result
        else:
            raise ValueError(f"未知模块名称: {module_name}")
    
    def set_baseline_mode(self):
        """将所有模块设置为基线模式（最简单配置）"""
        self.toggle_module("text_attention", False)
        self.toggle_module("hierarchical", False)
        self.toggle_module("history_gru", False)
        self.toggle_module("fusion", False)
        self.toggle_module("quality_head", False)
        logger.info("已切换到基线模式")
    
    def set_advanced_mode(self):
        """将所有模块设置为高级模式（所有功能开启）"""
        self.toggle_module("text_attention", True)
        self.toggle_module("hierarchical", True)
        self.toggle_module("history_gru", True)
        self.toggle_module("fusion", True)
        self.toggle_module("quality_head", True)
        logger.info("已切换到高级模式")
    
    def process_query(self, query: str) -> torch.Tensor:
        """从原始查询文本处理为特征向量"""
        # 编码文本为向量
        query_tensor = self.text_encoder(query)
        
        # 应用层级注意力（如果启用）
        query_features = self.hierarchical_attention(query_tensor)
        
        return query_features
    
    def process_history(
        self, 
        history: List[str], 
        max_len: Optional[int] = None
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        处理用户历史意图
        
        Args:
            history: 用户历史意图列表
            max_len: 最大历史长度，默认使用模型配置的max_history_len
            
        Returns:
            历史张量和长度张量的元组
        """
        max_len = max_len or self.max_history_len
        # 将历史动作转换为ID
        history_ids = []
        for intent in history[-max_len:]:
            if intent in self.intent_to_id:
                history_ids.append(self.intent_to_id[intent])
            else:
                # 未知意图使用特殊ID
                history_ids.append(self.intent_space_size)
        
        # 填充序列
        padded_history = [0] * max_len  # 0作为填充
        length = min(len(history_ids), max_len)
        padded_history[-length:] = history_ids[-length:]
        
        # 转换为张量
        history_tensor = torch.tensor(padded_history, dtype=torch.long).unsqueeze(0).to(self.device)
        length_tensor = torch.tensor([length], dtype=torch.long).to(self.device)
        
        return history_tensor, length_tensor
    
    def forward(
        self, 
        query: Union[str, torch.Tensor],
        history: Union[List[str], torch.Tensor],
        history_lengths: Optional[torch.Tensor] = None
    ) -> Dict[str, torch.Tensor]:
        """
        模型前向传播
        
        Args:
            query: 用户查询文本或特征向量
            history: 用户历史意图列表或张量
            history_lengths: 历史长度张量(如果history是张量)
            
        Returns:
            包含预测结果的字典
        """
        # 处理查询
        if isinstance(query, str):
            query_features = self.process_query(query)
        else:
            # 如果是已编码的向量，直接使用
            query_features = query
        
        # 处理历史
        if isinstance(history, list):
            history_tensor, history_lengths = self.process_history(history)
        else:
            # 如果已经是张量，直接使用
            history_tensor = history
            assert history_lengths is not None, "提供张量历史时必须提供history_lengths"
        
        # 编码历史
        history_features = self.history_encoder(history_tensor, history_lengths)
        
        # 特征融合
        combined = torch.cat([query_features, history_features], dim=1)
        fusion_features = self.fusion_layer(combined)
        
        # 意图预测
        intent_logits = self.decision_head(fusion_features)
        intent_probs = F.softmax(intent_logits, dim=1)
        
        # 质量评分
        if self.config["use_quality_head"]:
            quality_score = torch.sigmoid(self.quality_head(fusion_features))
        else:
            # 不使用质量头时，置信度为1.0
            quality_score = torch.ones_like(intent_probs[:, 0:1])
        
        return {
            "intent_logits": intent_logits,
            "intent_probs": intent_probs,
            "quality_score": quality_score,
            "features": fusion_features  # 返回特征以便进一步分析
        }
    
    def predict(
        self,
        query: str, 
        history: List[str] = None
    ) -> Dict[str, Any]:
        """
        预测用户意图
        
        Args:
            query: 用户查询文本
            history: 用户历史意图列表
            
        Returns:
            包含预测意图和置信度的字典
        """
        self.eval()
        with torch.no_grad():
            # 获取输入
            history = history or []
            
            # 模型推理
            outputs = self.forward(query, history)
            
            # 获取预测结果
            intent_probs = outputs["intent_probs"].cpu().numpy()[0]
            quality_score = outputs["quality_score"].cpu().item()
            
            # 找出最可能的意图
            top_intent_idx = np.argmax(intent_probs)
            top_intent = self.id_to_intent[top_intent_idx]
            top_prob = float(intent_probs[top_intent_idx])
            
            # 构建置信度调整后的意图分布
            adjusted_probs = intent_probs * quality_score
            confident = top_prob * quality_score >= self.confidence_threshold
            
            # 构建Top-3意图
            sorted_indices = np.argsort(intent_probs)[::-1][:3]
            top_intents = [
                {
                    "intent": self.id_to_intent[idx],
                    "probability": float(intent_probs[idx]),
                    "adjusted_prob": float(intent_probs[idx] * quality_score)
                }
                for idx in sorted_indices
            ]
            
            return {
                "predicted_intent": top_intent,
                "confidence": float(top_prob),
                "quality_score": float(quality_score),
                "adjusted_confidence": float(top_prob * quality_score),
                "is_confident": confident,
                "top_intents": top_intents,
                "active_modules": self.get_active_modules()
            }
    
    def get_active_modules(self) -> Dict[str, bool]:
        """获取当前启用的模块"""
        return {
            "text_attention": self.config["use_text_attention"],
            "hierarchical": self.config["use_hierarchical"],
            "history_gru": self.config["use_history_gru"],
            "fusion": self.config["use_fusion"],
            "quality_head": self.config["use_quality_head"]
        }
    
    def save_model(self, path: Optional[str] = None):
        """保存模型"""
        if path is None:
            # 生成默认路径
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(self.model_dir, f"intent_policy_{timestamp}.pt")
        
        # 保存模型状态和配置
        save_data = {
            "model_state": self.state_dict(),
            "intent_types": self.intent_types,
            "config": self.config,
            "confidence_threshold": self.confidence_threshold,
            "version": self.model_version,
            "timestamp": datetime.now().isoformat(),
            "active_modules": self.get_active_modules()
        }
        
        torch.save(save_data, path)
        logger.info(f"模型已保存到: {path}")
        
        # 清理旧模型
        if self.auto_save and self.keep_last_n > 0:
            self._cleanup_old_models()
    
    def _cleanup_old_models(self):
        """清理旧模型，只保留最新的N个"""
        models = [f for f in os.listdir(self.model_dir) if f.startswith("intent_policy_") and f.endswith(".pt")]
        if len(models) <= self.keep_last_n:
            return
        
        # 按时间排序
        models.sort(reverse=True)
        
        # 删除多余的模型
        for old_model in models[self.keep_last_n:]:
            try:
                os.remove(os.path.join(self.model_dir, old_model))
                logger.info(f"已删除旧模型: {old_model}")
            except Exception as e:
                logger.warning(f"删除旧模型失败: {e}")
    
    def load_model(self, path: str):
        """加载模型"""
        try:
            data = torch.load(path, map_location=self.device)
            
            # 更新配置
            if "intent_types" in data and data["intent_types"] != self.intent_types:
                logger.warning(f"模型意图类型不匹配: 当前{len(self.intent_types)}个, 模型{len(data['intent_types'])}个")
                if len(data["intent_types"]) != len(self.intent_types):
                    raise ValueError("意图类型数量不匹配，无法加载模型")
            
            # 加载模块配置
            if "config" in data:
                old_config = self.config.copy()
                self.config.update(data["config"])
                
                # 如果配置有变化，需要重新创建对应模块
                if old_config != self.config:
                    # 更新文本编码器
                    self.text_encoder = TextEncoder(
                        embedding_model=self.embedding_model,
                        use_attention=self.config["use_text_attention"],
                        proj_dim=self.config["embed_dim"]
                    ).to(self.device)
                    
                    # 更新历史编码器
                    self.history_encoder = HistoryEncoder(
                        action_space_size=self.intent_space_size + 1,
                        use_gru=self.config["use_history_gru"],
                        hidden_dim=self.config["history_dim"]
                    ).to(self.device)
                    
                    # 更新模块状态
                    self.hierarchical_attention.enabled = self.config["use_hierarchical"]
                    self.fusion_layer.enabled = self.config["use_fusion"]
                    self.quality_head.enabled = self.config["use_quality_head"]
            
            # 加载模型状态
            self.load_state_dict(data["model_state"])
            
            # 更新其他配置
            self.confidence_threshold = data.get("confidence_threshold", self.confidence_threshold)
            self.max_history_len = data.get("max_history_len", self.max_history_len)
            self.model_version = data.get("version", self.model_version)
            
            logger.info(f"成功加载模型: {path}")
            logger.info(f"活跃模块: {self.get_active_modules()}")
            return True
        except Exception as e:
            logger.error(f"加载模型失败: {e}")
            traceback.print_exc()
            return False
