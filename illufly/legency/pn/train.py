import os
import json
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import logging

from torch.utils.data import Dataset, DataLoader
from typing import List, Dict, Any, Optional
from tqdm import tqdm

from ..community import OpenAIEmbeddings
from .intent_policy import EnhancedIntentPolicyNetwork
from .intent_data import IntentDataset

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def custom_collate(batch):
    """处理不同长度的样本批次"""
    # 过滤掉空的或无效的样本
    batch = [b for b in batch if b is not None and all(k in b for k in ['query_embed', 'intent_id', 'history', 'history_len'])]
    
    if not batch:
        return None  # 如果批次为空，返回None
    
    # 检查历史张量的形状并打印出来
    history_shapes = [item['history'].shape for item in batch]
    if len(set(str(shape) for shape in history_shapes)) > 1:
        print(f"警告：批次中的历史张量形状不一致: {history_shapes}")
        
        # 统一历史张量的形状
        max_len = max(s[0] for s in history_shapes if len(s) > 0)
        for i, item in enumerate(batch):
            if item['history'].shape[0] == 0 or item['history'].shape[0] < max_len:
                # 创建一个适当尺寸的零张量
                batch[i]['history'] = torch.zeros(max_len, dtype=torch.long)
                batch[i]['history_len'] = torch.tensor(0, dtype=torch.long)
    
    # 分别处理每个字段
    try:
        query_embeds = torch.stack([item['query_embed'] for item in batch])
        intent_ids = torch.stack([item['intent_id'] for item in batch])
        history = torch.stack([item['history'] for item in batch])
        history_len = torch.stack([item['history_len'] for item in batch])
        
        # 元数据保持为列表
        metadata = [item['metadata'] for item in batch]
        
        return {
            'query_embed': query_embeds,
            'intent_id': intent_ids,
            'history': history,
            'history_len': history_len,
            'metadata': metadata
        }
    except Exception as e:
        print(f"在合并批次时出错: {e}")
        print(f"批次大小: {len(batch)}")
        print(f"样本字段: {list(batch[0].keys())}")
        
        # 返回一个空批次
        return None

def train_intent_policy(
    train_data: List[Dict[str, Any]],
    val_data: Optional[List[Dict[str, Any]]] = None,
    intent_types: Optional[List[str]] = None,
    epochs: int = 20,
    batch_size: int = 32,
    embedding_model: Optional[OpenAIEmbeddings] = None,
    model_path: Optional[str] = None,
    max_history_len: int = 10,
    early_stopping: int = 5,
    learning_rate: float = 1e-4,
    output_dir: Optional[str] = "./models",
    use_text_attention: bool = True,
    use_hierarchical: bool = True,
    use_history_gru: bool = True,
    use_fusion: bool = True,
    use_quality_head: bool = True,
    model_mode: Optional[str] = None
):
    """
    训练意图策略网络
    
    Args:
        train_data: 训练数据列表
        val_data: 验证数据列表
        intent_types: 意图类型列表，如果为None则从数据中提取
        epochs: 训练轮数
        batch_size: 批量大小
        embedding_model: 嵌入模型
        model_path: 预训练模型路径
        max_history_len: 最大历史长度
        early_stopping: 早停轮数
        learning_rate: 学习率
        output_dir: 输出目录
        use_text_attention: 是否使用文本自注意力
        use_hierarchical: 是否使用层级注意力
        use_history_gru: 是否使用GRU处理历史
        use_fusion: 是否使用复杂融合层
        use_quality_head: 是否使用质量评估头
        model_mode: 预设模型模式，会覆盖个别模块设置
    
    Returns:
        训练好的模型
    """
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    # 提取或验证意图类型
    if intent_types is None:
        # 从数据中提取所有意图类型
        intent_types = sorted(list(set(item["intent"] for item in train_data)))
        logger.info(f"从数据中提取了{len(intent_types)}种意图类型")
    
    # 准备数据集
    train_dataset = IntentDataset(
        train_data, 
        intent_types=intent_types,
        embedding_model=embedding_model,
        max_history_len=max_history_len
    )
    
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=0,
        collate_fn=custom_collate
    )
    
    # 如果有验证集，准备验证集
    val_loader = None
    if val_data:
        val_dataset = IntentDataset(
            val_data,
            intent_types=intent_types,
            embedding_model=train_dataset.embedding_model,  # 共用嵌入模型
            max_history_len=max_history_len
        )
        
        val_loader = DataLoader(
            val_dataset,
            batch_size=batch_size,
            shuffle=False,
            num_workers=0,
            collate_fn=custom_collate
        )
    
    # 初始化模型
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = EnhancedIntentPolicyNetwork(
        intent_types=intent_types,
        embeddings=train_dataset.embedding_model,
        max_history_len=max_history_len,
        model_path=model_path,
        use_text_attention=use_text_attention,
        use_hierarchical=use_hierarchical,
        use_history_gru=use_history_gru,
        use_fusion=use_fusion,
        use_quality_head=use_quality_head
    )
    model.to(device)
    
    # 如果指定了模式，则切换到该模式
    if model_mode == "baseline":
        model.set_baseline_mode()
        logger.info("使用基线模式进行训练（所有高级模块关闭）")
    elif model_mode == "advanced":
        model.set_advanced_mode()
        logger.info("使用高级模式进行训练（所有模块开启）")
    
    # 记录当前使用的模块配置
    logger.info(f"训练模型配置: {model.get_active_modules()}")
    
    # 设置优化器
    optimizer = optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-5)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', factor=0.5, patience=3
    )
    
    # 损失函数
    criterion = nn.CrossEntropyLoss()
    
    # 训练记录
    best_val_loss = float('inf')
    best_epoch = 0
    no_improve_count = 0
    history = {
        "train_loss": [],
        "val_loss": [],
        "accuracy": []
    }
    
    # 开始训练
    logger.info(f"开始训练，共{epochs}轮，设备: {device}")
    
    for epoch in range(epochs):
        # 训练阶段
        model.train()
        train_loss = 0.0
        train_steps = 0
        
        for batch in tqdm(train_loader, desc=f"Epoch {epoch+1}/{epochs} [Train]"):
            # 获取数据
            query_embeds = batch["query_embed"].to(device)
            intent_ids = batch["intent_id"].to(device)
            history_tensor = batch["history"].to(device)
            history_len = batch["history_len"].to(device)
            
            # 前向传播
            outputs = model(query_embeds, history_tensor, history_len)
            logits = outputs["intent_logits"]
            
            # 计算损失
            loss = criterion(logits, intent_ids)
            
            # 反向传播
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            
            # 累计损失
            train_loss += loss.item()
            train_steps += 1
        
        avg_train_loss = train_loss / train_steps
        history["train_loss"].append(avg_train_loss)
        
        # 验证阶段
        if val_loader:
            model.eval()
            val_loss = 0.0
            val_steps = 0
            correct = 0
            total = 0
            
            with torch.no_grad():
                for batch in tqdm(val_loader, desc=f"Epoch {epoch+1}/{epochs} [Val]"):
                    # 获取数据
                    query_embeds = batch["query_embed"].to(device)
                    intent_ids = batch["intent_id"].to(device)
                    history_tensor = batch["history"].to(device)
                    history_len = batch["history_len"].to(device)
                    
                    # 前向传播
                    outputs = model(query_embeds, history_tensor, history_len)
                    logits = outputs["intent_logits"]
                    
                    # 计算损失
                    loss = criterion(logits, intent_ids)
                    
                    # 累计损失
                    val_loss += loss.item()
                    val_steps += 1
                    
                    # 计算准确率
                    _, predicted = torch.max(logits, 1)
                    total += intent_ids.size(0)
                    correct += (predicted == intent_ids).sum().item()
            
            avg_val_loss = val_loss / val_steps
            accuracy = correct / total
            
            history["val_loss"].append(avg_val_loss)
            history["accuracy"].append(accuracy)
            
            # 更新学习率
            old_lr = optimizer.param_groups[0]['lr']
            scheduler.step(avg_val_loss)
            new_lr = optimizer.param_groups[0]['lr']
            
            if new_lr != old_lr:
                logger.info(f"学习率从 {old_lr:.6f} 调整为 {new_lr:.6f}")
            
            # 打印信息
            logger.info(
                f"Epoch {epoch+1}/{epochs} - "
                f"Train Loss: {avg_train_loss:.4f}, "
                f"Val Loss: {avg_val_loss:.4f}, "
                f"Accuracy: {accuracy:.4f}"
                f"LR: {new_lr:.6f}"
            )
            
            # 检查是否有改进
            if avg_val_loss < best_val_loss:
                best_val_loss = avg_val_loss
                best_epoch = epoch
                no_improve_count = 0
                
                # 保存最佳模型
                best_model_path = os.path.join(output_dir, f"intent_policy_best.pt")
                model.save_model(best_model_path)
                logger.info(f"保存最佳模型，验证损失: {best_val_loss:.4f}")
                
                # 在保存模型时记录额外信息
                model_config = model.get_active_modules()
                with open(os.path.join(output_dir, "model_config.json"), 'w') as f:
                    json.dump(model_config, f, indent=2)
                logger.info(f"模型配置已保存到: {os.path.join(output_dir, 'model_config.json')}")
            else:
                no_improve_count += 1
                logger.info(f"验证损失未改进，连续{no_improve_count}轮")
            
            # 早停
            if no_improve_count >= early_stopping:
                logger.info(f"早停触发，连续{early_stopping}轮未改进")
                break
        else:
            # 无验证集时，每轮保存模型
            logger.info(f"Epoch {epoch+1}/{epochs} - Train Loss: {avg_train_loss:.4f}")
            if (epoch + 1) % 5 == 0:  # 每5轮保存一次
                model_path = os.path.join(output_dir, f"intent_policy_epoch_{epoch+1}.pt")
                model.save_model(model_path)
    
    # 保存最终模型
    final_model_path = os.path.join(output_dir, f"intent_policy_final.pt")
    model.save_model(final_model_path)
    
    # 如果有早停，加载最佳模型
    if val_loader and best_epoch < epoch:
        best_model_path = os.path.join(output_dir, f"intent_policy_best.pt")
        model.load_model(best_model_path)
        logger.info(f"加载最佳模型 (Epoch {best_epoch+1}, Val Loss: {best_val_loss:.4f})")
    
    # 保存训练历史
    history_path = os.path.join(output_dir, "training_history.json")
    with open(history_path, 'w') as f:
        # 将numpy数组转换为列表
        hist_dict = {k: [float(i) for i in v] for k, v in history.items()}
        json.dump(hist_dict, f, indent=2)
    
    return model 