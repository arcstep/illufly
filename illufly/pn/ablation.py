import os
import json
import itertools
from typing import List, Dict, Any, Optional
import logging

from .train import train_intent_policy

logger = logging.getLogger(__name__)

def run_ablation_study(
    train_data: List[Dict[str, Any]],
    val_data: List[Dict[str, Any]],
    intent_types: List[str],
    output_dir: str = "./ablation_results",
    configurations: Optional[List[Dict[str, bool]]] = None
):
    """
    运行消融实验，测试不同模块配置的性能
    
    Args:
        train_data: 训练数据
        val_data: 验证数据
        intent_types: 意图类型列表
        output_dir: 输出目录
        configurations: 要测试的配置列表，如果为None则生成所有可能组合
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # 如果未指定配置，生成所有可能的模块组合
    if configurations is None:
        modules = ["use_text_attention", "use_hierarchical", "use_history_gru", "use_fusion", "use_quality_head"]
        # 生成所有可能的开关组合
        all_combinations = list(itertools.product([True, False], repeat=len(modules)))
        
        configurations = []
        for combination in all_combinations:
            config = {module: value for module, value in zip(modules, combination)}
            # 添加配置名称
            enabled_modules = [m.replace("use_", "") for m, v in config.items() if v]
            config_name = "_".join(enabled_modules) if enabled_modules else "baseline"
            config["name"] = config_name
            configurations.append(config)
    
    # 添加基线和高级配置（如果不在列表中）
    has_baseline = any(all(not v for k, v in c.items() if k != "name") for c in configurations)
    has_advanced = any(all(v for k, v in c.items() if k != "name") for c in configurations)
    
    if not has_baseline:
        configurations.append({
            "name": "baseline",
            "use_text_attention": False,
            "use_hierarchical": False,
            "use_history_gru": False,
            "use_fusion": False,
            "use_quality_head": False
        })
    
    if not has_advanced:
        configurations.append({
            "name": "advanced",
            "use_text_attention": True,
            "use_hierarchical": True,
            "use_history_gru": True,
            "use_fusion": True,
            "use_quality_head": True
        })
    
    # 运行每个配置的实验
    results = []
    for config in configurations:
        config_name = config.pop("name", "unnamed")
        logger.info(f"开始训练配置: {config_name}")
        
        # 为此配置创建子目录
        config_dir = os.path.join(output_dir, config_name)
        os.makedirs(config_dir, exist_ok=True)
        
        # 训练模型
        model = train_intent_policy(
            train_data=train_data,
            val_data=val_data,
            intent_types=intent_types,
            output_dir=config_dir,
            **config
        )
        
        # 保存配置信息
        with open(os.path.join(config_dir, "config.json"), 'w') as f:
            json.dump(config, f, indent=2)
        
        # 记录结果
        val_accuracy = max(model.history["accuracy"]) if hasattr(model, "history") else None
        results.append({
            "config_name": config_name,
            "config": config,
            "val_accuracy": val_accuracy,
            "model_path": os.path.join(config_dir, "intent_policy_best.pt")
        })
    
    # 保存所有结果的摘要
    with open(os.path.join(output_dir, "ablation_results.json"), 'w') as f:
        json.dump(results, f, indent=2)
    
    # 输出结果摘要
    logger.info("消融实验完成，结果摘要:")
    for result in sorted(results, key=lambda x: x.get("val_accuracy", 0), reverse=True):
        logger.info(f"配置: {result['config_name']}, 验证准确率: {result.get('val_accuracy', 'N/A')}")
    
    return results 