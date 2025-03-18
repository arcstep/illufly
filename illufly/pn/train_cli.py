#!/usr/bin/env python
import os
import sys
import argparse
import json
import logging
import torch

from typing import List, Dict, Any, Optional

from ..community import OpenAIEmbeddings
from .train import train_intent_policy
from .ablation import run_ablation_study

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def parse_args():
    parser = argparse.ArgumentParser(description='训练意图策略网络')
    
    # 添加数据集参数
    parser.add_argument('--train-data', type=str, required=True, help='训练数据的JSON文件路径')
    parser.add_argument('--val-data', type=str, help='验证数据的JSON文件路径')
    parser.add_argument('--intent-types', type=str, nargs='+', help='意图类型列表')
    
    # 添加新参数
    parser.add_argument('--validate-data', action='store_true', help='验证并修复数据集')
    
    # 训练参数
    parser.add_argument(
        "--epochs", type=int, default=2,
        help="训练轮数"
    )
    parser.add_argument(
        "--batch-size", type=int, default=32,
        help="批量大小"
    )
    parser.add_argument(
        "--lr", "--learning-rate", type=float, default=1e-4,
        help="学习率"
    )
    parser.add_argument(
        "--early-stopping", type=int, default=5,
        help="早停轮数"
    )
    parser.add_argument(
        "--max-history-len", type=int, default=10,
        help="最大历史长度"
    )
    
    # 模型配置
    parser.add_argument(
        "--model-path",
        help="预训练模型路径，用于继续训练"
    )
    parser.add_argument(
        "--output-dir", default="./models",
        help="模型输出目录"
    )
    parser.add_argument(
        "--model-mode", choices=["baseline", "advanced", None],
        help="模型模式，baseline(所有高级特性关闭)或advanced(所有特性开启)"
    )
    
    # 模块开关 - 使用否定形式以默认启用所有模块
    parser.add_argument(
        "--no-text-attention", action="store_true",
        help="禁用文本自注意力"
    )
    parser.add_argument(
        "--no-hierarchical", action="store_true",
        help="禁用层级注意力"
    )
    parser.add_argument(
        "--no-history-gru", action="store_true",
        help="禁用GRU历史处理"
    )
    parser.add_argument(
        "--no-fusion", action="store_true",
        help="禁用复杂融合层"
    )
    parser.add_argument(
        "--no-quality-head", action="store_true",
        help="禁用质量评估头"
    )
    
    # 嵌入模型配置
    parser.add_argument(
        "--embedding-model", default="text-embedding-ada-002",
        help="嵌入模型名称"
    )
    parser.add_argument(
        "--imitator", 
        help="嵌入模型imitator"
    )
    
    # 消融实验
    parser.add_argument(
        "--ablation-study", action="store_true",
        help="运行消融实验，测试不同模块组合的效果"
    )
    parser.add_argument(
        "--ablation-output-dir", default="./ablation_results",
        help="消融实验结果输出目录"
    )
    
    return parser.parse_args()

def main():
    """
    意图策略网络训练命令行工具
    使用示例:
    
    # 基本训练
    python -m illufly.pn.train_cli \
        --train-data ./intent_data/train_data_20250319_005801.json \
        --model-mode baseline
    
    # 使用高级模式（所有特性都启用）
    python -m illufly.pn.train_cli \
        --train-data ./intent_data/train_data.json \
        --val-data ./intent_data/val_data.json \
        --model-mode advanced \
        --epochs 30 \
        --batch-size 64
    
    # 禁用文本注意力和层级注意力
    python -m illufly.pn.train_cli \
        --train-data ./intent_data/train_data_20250319_005801.json \
        --no-text-attention \
        --no-hierarchical \
        --epochs 20
    
    # 运行消融实验
    python -m illufly.pn.train_cli \
        --train-data ./intent_data/train_data.json \
        --val-data ./intent_data/val_data.json \
        --ablation-study
        --ablation-output-dir ./results/ablation

    # 明确指定意图类型和嵌入模型
    python -m illufly.pn.train_cli \
        --train-data ./intent_data/train_data_20250319_005801.json \
        --intent-types "查询余额" "转账" "修改信息" "技术支持" \
        --embedding-model "text-embedding-3-small" \
        --imitator "OPENAI"
    
    """
    args = parse_args()
    
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 总是验证数据集
    print("自动验证训练数据...")
    args.train_data = validate_dataset(args.train_data, args.intent_types)
    if args.val_data:
        print("自动验证验证数据...")
        args.val_data = validate_dataset(args.val_data, args.intent_types)
    
    # 加载训练数据
    with open(args.train_data, 'r', encoding='utf-8') as f:
        train_data = json.load(f)
    
    # 加载验证数据
    val_data = None
    if args.val_data:
        with open(args.val_data, 'r', encoding='utf-8') as f:
            val_data = json.load(f)
    
    # 初始化嵌入模型
    embedding_model = OpenAIEmbeddings(
        model=args.embedding_model,
        imitator=args.imitator,
        dim=1536  # 默认维度
    )
    
    # 提取意图类型
    intent_types = args.intent_types
    if not intent_types:
        intent_types = sorted(list(set(item.get("intent") for item in train_data if "intent" in item)))
        logger.info(f"从数据中提取了意图类型: {', '.join(intent_types)}")
    
    # 检查设备
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"使用设备: {device}")
    
    # 如果是消融实验
    if args.ablation_study:
        logger.info("开始运行消融实验...")
        results = run_ablation_study(
            train_data=train_data,
            val_data=val_data,
            intent_types=intent_types,
            output_dir=args.ablation_output_dir
        )
        logger.info(f"消融实验完成，结果已保存到 {args.ablation_output_dir}")
        return
    
    # 模块配置
    module_config = {
        "use_text_attention": not args.no_text_attention,
        "use_hierarchical": not args.no_hierarchical,
        "use_history_gru": not args.no_history_gru,
        "use_fusion": not args.no_fusion,
        "use_quality_head": not args.no_quality_head
    }
    
    # 显示训练配置
    logger.info("训练配置:")
    logger.info(f"  - 训练轮数: {args.epochs}")
    logger.info(f"  - 批量大小: {args.batch_size}")
    logger.info(f"  - 学习率: {args.lr}")
    logger.info(f"  - 早停轮数: {args.early_stopping}")
    logger.info(f"  - 最大历史长度: {args.max_history_len}")
    logger.info(f"  - 模型模式: {args.model_mode or '自定义'}")
    logger.info("  - 模块配置:")
    for module, enabled in module_config.items():
        logger.info(f"    - {module}: {'启用' if enabled else '禁用'}")
    
    # 开始训练
    logger.info("开始训练...")
    model = train_intent_policy(
        train_data=train_data,
        val_data=val_data,
        intent_types=intent_types,
        epochs=args.epochs,
        batch_size=args.batch_size,
        embedding_model=embedding_model,
        model_path=args.model_path,
        max_history_len=args.max_history_len,
        early_stopping=args.early_stopping,
        learning_rate=args.lr,
        output_dir=args.output_dir,
        model_mode=args.model_mode,
        **module_config
    )
    
    logger.info(f"训练完成，模型已保存到 {args.output_dir}")
    
    # 显示最终模型配置
    active_modules = model.get_active_modules()
    logger.info("最终模型配置:")
    for module, enabled in active_modules.items():
        logger.info(f"  - {module}: {'启用' if enabled else '禁用'}")

def validate_dataset(dataset_path, intent_types=None):
    """验证数据集并修复常见问题"""
    print(f"验证数据集: {dataset_path}")
    
    try:
        with open(dataset_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"无法加载数据集: {e}")
        return dataset_path
    
    if not intent_types:
        # 尝试从数据中提取意图类型
        intent_types = list(set(item.get("intent", "") for item in data if "intent" in item))
        print(f"从数据中提取到的意图类型: {intent_types}")
    
    intent_to_id = {intent: i for i, intent in enumerate(intent_types)} if intent_types else {}
    
    valid_count = 0
    fixed_data = []
    
    for i, item in enumerate(data):
        valid = True
        fixed_item = item.copy()
        
        # 检查必要字段
        if 'query' not in item or not item['query']:
            print(f"样本 {i}: 缺少查询字段")
            fixed_item['query'] = "默认查询"
            valid = False
        
        if 'intent' not in item or not item['intent']:
            print(f"样本 {i}: 缺少意图字段")
            fixed_item['intent'] = intent_types[0] if intent_types else "默认"
            valid = False
        elif intent_types and item['intent'] not in intent_to_id:
            print(f"样本 {i}: 未知意图 '{item['intent']}'")
            fixed_item['intent'] = intent_types[0] if intent_types else "默认"
            valid = False
        
        # 检查历史
        if 'history' not in item:
            print(f"样本 {i}: 缺少历史字段")
            fixed_item['history'] = []
            valid = False
        elif not isinstance(item['history'], list):
            print(f"样本 {i}: 历史字段不是列表")
            fixed_item['history'] = []
            valid = False
        
        # 确保历史中的所有元素都是有效意图
        if 'history' in fixed_item and isinstance(fixed_item['history'], list):
            valid_history = []
            for h_intent in fixed_item['history']:
                if not intent_types or h_intent in intent_to_id:
                    valid_history.append(h_intent)
                else:
                    print(f"样本 {i}: 历史中存在未知意图 '{h_intent}'")
                    valid = False
            fixed_item['history'] = valid_history
        
        fixed_data.append(fixed_item)
        if valid:
            valid_count += 1
    
    print(f"验证结果: {valid_count}/{len(data)} 样本有效")
    
    # 保存修复后的数据集
    if valid_count < len(data):
        fixed_path = dataset_path.replace('.json', '_fixed.json')
        with open(fixed_path, 'w', encoding='utf-8') as f:
            json.dump(fixed_data, f, ensure_ascii=False, indent=2)
        print(f"已将修复后的数据集保存到: {fixed_path}")
        return fixed_path
    
    return dataset_path

if __name__ == "__main__":
    main() 