import json
import glob
import os
from typing import List, Dict, Any
from tqdm import tqdm  # 进度条支持

def merge_policy_data(
    input_dir: str = "tests/pn/data",
    output_file: str = "tests/pn/data/policy_data_merged.json",
    pattern: str = "policy_data_batch_*.json"
) -> None:
    """
    合并策略训练数据文件
    
    参数:
    input_dir: 输入目录路径
    output_file: 输出文件路径
    pattern: 文件匹配模式
    """
    # 获取文件列表并按批次排序
    file_paths = sorted(
        glob.glob(os.path.join(input_dir, pattern)),
        key=lambda x: int(x.split("_")[-2])  # 按批次号排序
    )
    
    merged_data: List[Dict[str, Any]] = []
    seen = set()  # 基于哈希的去重集合
    
    print(f"发现 {len(file_paths)} 个数据文件需要处理...")
    
    for file_path in tqdm(file_paths, desc="合并进度"):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                batch_data = json.load(f)
                
                for item in batch_data:
                    # 生成唯一标识键（组合关键字段）
                    unique_key = (
                        item["user_query"],
                        item["action_type"],
                        str(item["action_params"])
                    )
                    item_hash = hash(unique_key)
                    
                    if item_hash not in seen:
                        seen.add(item_hash)
                        merged_data.append(item)
                        
        except Exception as e:
            print(f"跳过损坏文件 {os.path.basename(file_path)}: {str(e)}")
            continue
    
    # 按时间戳排序（如果需要时间顺序）
    merged_data.sort(key=lambda x: x["timestamp"])
    
    # 保存合并结果
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(merged_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n合并完成！共处理 {len(merged_data)} 条唯一数据")
    print(f"输出文件: {os.path.abspath(output_file)}")

if __name__ == "__main__":
    # 使用示例（可通过命令行参数覆盖）
    merge_policy_data()