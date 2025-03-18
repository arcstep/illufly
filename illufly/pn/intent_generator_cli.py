#!/usr/bin/env python
import os
import sys
import asyncio
import argparse
import json

from typing import List, Dict, Any, Optional
from datetime import datetime

from .intent_generator import IntentDataGenerator

async def main():
    """
    使用示例

    # 使用指定的意图列表生成数据
    python -m illufly.pn.intent_generator_cli --intent "查询余额" "转账" "修改信息" "技术支持"

    # 为多个领域生成数据
    python -m illufly.pn.intent_generator_cli \
    --intent "查询余额" "转账" "账单查询" "投诉" \
    --domains "银行" "保险" "电商" \
    --batch-size 10

    # 指定意图分布权重
    python -m illufly.pn.intent_generator_cli \
    --intent "查询余额" "转账" "账单查询" "投诉" \
    --intent-dist "查询余额:0.4" "转账:0.3" "账单查询:0.2" "投诉:0.1"

    # 使用自定义提示词文件
    python -m illufly.pn.intent_generator_cli \
    --intent "查询余额" "转账" "账单查询" \
    --system-prompt ./prompts/system_prompt.txt \
    --user-prompt ./prompts/user_prompt.txt

    # 生成数据并拆分为训练集和验证集
    python -m illufly.pn.intent_generator_cli \
    --intent "查询余额" "转账" "账单查询" "投诉" "技术支持" \
    --domains "银行" "电商" \
    --split --val-ratio 0.2 --balance

    # 使用全部配置选项的示例
    python -m illufly.pn.intent_generator_cli \
    --intent "查询余额" "转账" "账单查询" "投诉" "技术支持" "产品咨询" "账户管理" \
    --output ./data/intent_data \
    --domains "银行" "保险" "证券" "电商" \
    --batches 10 \
    --batch-size 8 \
    --history-len 4 \
    --vary-history \
    --model "gpt-4o" \
    --temperature 0.8 \
    --intent-dist "查询余额:0.25" "转账:0.2" "产品咨询:0.15" \
    --split --val-ratio 0.15 --balance

    """
    # 创建参数解析器
    parser = argparse.ArgumentParser(
        description="意图数据生成工具 - 生成策略网络训练数据",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # 必要参数
    parser.add_argument(
        "--intent", "-i", nargs="+", required=True,
        help="指定意图类型列表，例如: --intent '查询余额' '转账' '技术支持'"
    )
    
    # 输出配置
    parser.add_argument(
        "--output", "-o", default="./intent_data",
        help="指定输出目录"
    )
    
    # 数据生成配置
    parser.add_argument(
        "--domains", "-d", nargs="+", default=[],
        help="指定领域列表，例如: --domains '银行' '电商' '旅游'"
    )
    parser.add_argument(
        "--batches", "-b", type=int, default=None,
        help="生成的批次数量（默认等于领域数量，如未指定领域则为1）"
    )
    parser.add_argument(
        "--batch-size", "-s", type=int, default=5,
        help="每批生成的样本数量"
    )
    parser.add_argument(
        "--history-len", "-hl", type=int, default=5,
        help="历史意图序列的最大长度"
    )
    parser.add_argument(
        "--vary-history", "-vh", action="store_true",
        help="生成不同长度的历史序列"
    )
    
    # LLM配置
    parser.add_argument(
        "--model", "-m", default="gpt-4o-mini",
        help="指定使用的LLM模型"
    )
    parser.add_argument(
        "--imitator", default=None,
        help="指定使用的imitator（替代实际OpenAI API的本地模型）"
    )
    parser.add_argument(
        "--temperature", "-t", type=float, default=0.7,
        help="LLM生成的温度参数"
    )
    
    # 意图分布配置
    parser.add_argument(
        "--intent-dist", "-id", nargs="+", default=[],
        help="意图分布参数，格式为'意图:权重'，例如: --intent-dist '查询余额:0.3' '转账:0.2'"
    )
    
    # 提示词配置
    parser.add_argument(
        "--system-prompt", default=None,
        help="自定义系统提示词文件路径"
    )
    parser.add_argument(
        "--user-prompt", default=None,
        help="自定义用户提示词文件路径"
    )
    
    # 数据集分割
    parser.add_argument(
        "--split", action="store_true",
        help="拆分数据为训练集和验证集"
    )
    parser.add_argument(
        "--val-ratio", type=float, default=0.2,
        help="验证集比例"
    )
    parser.add_argument(
        "--balance", action="store_true",
        help="平衡各意图在训练和验证集中的分布"
    )
    
    # 解析参数
    args = parser.parse_args()
    
    # 处理意图分布
    intent_distribution = None
    if args.intent_dist:
        intent_distribution = {}
        for item in args.intent_dist:
            if ":" in item:
                intent, weight = item.split(":", 1)
                try:
                    intent_distribution[intent] = float(weight)
                except ValueError:
                    print(f"警告: 忽略无效的意图分布参数 '{item}'")
    
    # 加载自定义提示词
    system_prompt = None
    user_prompt = None
    
    if args.system_prompt:
        try:
            with open(args.system_prompt, 'r', encoding='utf-8') as f:
                system_prompt = f.read()
        except Exception as e:
            print(f"警告: 无法加载系统提示词文件: {e}")
    
    if args.user_prompt:
        try:
            with open(args.user_prompt, 'r', encoding='utf-8') as f:
                user_prompt = f.read()
        except Exception as e:
            print(f"警告: 无法加载用户提示词文件: {e}")
    
    # 创建意图数据生成器
    generator = IntentDataGenerator(
        output_dir=args.output,
        model=args.model,
        imitator=args.imitator,
        batch_size=args.batch_size,
        temperature=args.temperature,
        intent_types=args.intent,
        max_history_len=args.history_len
    )
    
    # 生成数据
    print(f"开始生成意图数据...")
    print(f"意图类型: {', '.join(args.intent)}")
    if args.domains:
        print(f"领域: {', '.join(args.domains)}")
    
    data = await generator.generate_intent_data(
        domains=args.domains if args.domains else None,
        system_prompt=system_prompt,
        user_prompt_template=user_prompt,
        num_batches=args.batches,
        intent_distribution=intent_distribution,
        vary_history_length=args.vary_history
    )
    
    if not data:
        print("错误: 未能生成任何数据")
        return
    
    print(f"成功生成 {len(data)} 条训练样本")
    
    # 如果需要，拆分数据集
    if args.split:
        train_data, val_data = generator.split_train_val(
            data,
            val_ratio=args.val_ratio,
            balance_intents=args.balance
        )
        
        # 保存拆分的数据集
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        train_file = os.path.join(args.output, f"train_data_{timestamp}.json")
        val_file = os.path.join(args.output, f"val_data_{timestamp}.json")
        
        with open(train_file, 'w', encoding='utf-8') as f:
            json.dump(train_data, f, ensure_ascii=False, indent=2)
        
        with open(val_file, 'w', encoding='utf-8') as f:
            json.dump(val_data, f, ensure_ascii=False, indent=2)
        
        print(f"已拆分数据集:")
        print(f"  训练集: {len(train_data)} 条样本，保存至 {train_file}")
        print(f"  验证集: {len(val_data)} 条样本，保存至 {val_file}")

if __name__ == "__main__":
    asyncio.run(main()) 