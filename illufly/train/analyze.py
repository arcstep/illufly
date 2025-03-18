# analyze.py
import argparse
import asyncio
import json
import os
import traceback
from typing import Any, Dict, List, Optional
from datetime import datetime
from collections import defaultdict

def analyze_data(
    data: List[Dict[str, Any]], 
    max_categories: int = 5,
    exclude_fields: List[str] = None,
    include_fields: List[str] = None,
    metadata_fields: List[str] = None
) -> str:
    """
    分析数据并生成文本报告
    
    Args:
        data: 要分析的数据列表
        max_categories: 每个字段最多显示的类别数量
        exclude_fields: 要排除的字段列表
        include_fields: 要包含的字段列表(如果指定，则只分析这些字段)
        metadata_fields: 要视为元数据的字段(用于分组分析)
    
    Returns:
        格式化的分析报告文本
    """
    if not data:
        return "无数据可分析"
        
    # 设置默认排除的字段
    if exclude_fields is None:
        exclude_fields = ['timestamp', 'batch_id']
    
    report_lines = []
    report_lines.append(f"数据分析报告 - 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"总样本数: {len(data)}")
    report_lines.append("=" * 50)
    
    # 获取所有可能的字段
    all_fields = set()
    for item in data:
        all_fields.update(item.keys())
    
    # 如果指定了要包含的字段，则只分析这些字段
    if include_fields:
        fields_to_analyze = [f for f in include_fields if f in all_fields]
    else:
        fields_to_analyze = [f for f in sorted(all_fields) if f not in exclude_fields]
    
    # 确定元数据字段，如果没有指定，则使用一些常见的元数据字段名称
    if metadata_fields is None:
        metadata_fields = ['domain', 'category', 'type', 'source']
        metadata_fields = [f for f in metadata_fields if f in all_fields]
    
    # 先分析元数据字段，这些通常是分类数据
    for field in [f for f in fields_to_analyze if f in metadata_fields]:
        report_lines.append(f"\n字段: {field} (元数据)")
        analyze_field(data, field, report_lines, max_categories)
        
    # 再分析其他数据字段
    for field in [f for f in fields_to_analyze if f not in metadata_fields]:
        report_lines.append(f"\n字段: {field}")
        analyze_field(data, field, report_lines, max_categories)
    
    # 返回完整的报告文本
    return "\n".join(report_lines)

def analyze_field(
    data: List[Dict[str, Any]],
    field: str,
    report_lines: List[str],
    max_categories: int = 5
) -> None:
    """分析单个字段并添加到报告中"""
    values = [item.get(field) for item in data if field in item]
    
    # 统计基本信息
    report_lines.append(f"  - 出现次数: {len(values)}/{len(data)} ({(len(values)/len(data)*100):.1f}%)")
    
    # 空值统计
    null_count = sum(1 for v in values if v is None)
    if null_count:
        report_lines.append(f"  - 空值数量: {null_count} ({(null_count/len(values)*100):.1f}%)")
    
    # 根据值类型进行统计
    if values:
        value_types = set(type(v).__name__ for v in values if v is not None)
        report_lines.append(f"  - 值类型: {', '.join(value_types)}")
        
        # 数值类型处理
        if all(isinstance(v, (int, float)) for v in values if v is not None):
            non_null = [v for v in values if v is not None]
            if non_null:
                report_lines.append(f"  - 最小值: {min(non_null)}")
                report_lines.append(f"  - 最大值: {max(non_null)}")
                report_lines.append(f"  - 平均值: {sum(non_null)/len(non_null):.2f}")
                
                # 值分布统计 - 只在类别较少时执行
                unique_values = set(non_null)
                if len(unique_values) <= 20:  # 最多统计20种不同值
                    value_counts = defaultdict(int)
                    for v in non_null:
                        value_counts[v] += 1
                    
                    # 只显示前N个最常见的值
                    most_common = sorted(value_counts.items(), key=lambda x: -x[1])
                    
                    # 如果类别太多，只显示摘要信息
                    if len(most_common) > max_categories:
                        top_values = most_common[:max_categories]
                        report_lines.append(f"  - 值分布 (显示前{max_categories}个，共{len(most_common)}个不同值):")
                        for val, count in top_values:
                            percent = (count / len(non_null)) * 100
                            bar = '#' * int(percent / 5)
                            report_lines.append(f"    {val}: {count} ({percent:.1f}%) {bar}")
                        other_count = sum(count for _, count in most_common[max_categories:])
                        other_percent = (other_count / len(non_null)) * 100
                        report_lines.append(f"    其他({len(most_common) - max_categories}个值): {other_count} ({other_percent:.1f}%)")
                    else:
                        report_lines.append("  - 值分布:")
                        for val, count in most_common:
                            percent = (count / len(non_null)) * 100
                            bar = '#' * int(percent / 5)
                            report_lines.append(f"    {val}: {count} ({percent:.1f}%) {bar}")
        
        # 字符串类型处理
        elif all(isinstance(v, str) for v in values if v is not None):
            non_null = [v for v in values if v is not None]
            if non_null:
                # 计算长度统计
                lengths = [len(v) for v in non_null]
                report_lines.append(f"  - 最短长度: {min(lengths)}")
                report_lines.append(f"  - 最长长度: {max(lengths)}")
                report_lines.append(f"  - 平均长度: {sum(lengths)/len(lengths):.1f}")
                
                # 值分布统计 - 只在不同值较少时显示
                unique_values = set(non_null)
                
                # 如果不同值太多，只显示类别数量
                if len(unique_values) > 30:
                    report_lines.append(f"  - 不同值数量: {len(unique_values)} (太多，不显示详细分布)")
                elif len(unique_values) > max_categories:
                    # 显示摘要信息
                    value_counts = defaultdict(int)
                    for v in non_null:
                        value_counts[v] += 1
                    
                    # 取最常见的几个值
                    most_common = sorted(value_counts.items(), key=lambda x: -x[1])[:max_categories]
                    report_lines.append(f"  - 值分布 (显示前{max_categories}个，共{len(unique_values)}个不同值):")
                    
                    for val, count in most_common:
                        percent = (count / len(non_null)) * 100
                        bar = '#' * int(percent / 5)
                        # 截断过长的值
                        display_val = val[:40] + "..." if len(val) > 40 else val
                        report_lines.append(f"    {display_val}: {count} ({percent:.1f}%) {bar}")
                    
                    other_count = sum(count for _, count in sorted(value_counts.items(), 
                                                                key=lambda x: -x[1])[max_categories:])
                    other_percent = (other_count / len(non_null)) * 100
                    report_lines.append(f"    其他({len(unique_values) - max_categories}个值): {other_count} ({other_percent:.1f}%)")
                else:
                    # 显示所有值
                    value_counts = defaultdict(int)
                    for v in non_null:
                        value_counts[v] += 1
                    
                    report_lines.append("  - 值分布:")
                    for val, count in sorted(value_counts.items(), key=lambda x: -x[1]):
                        percent = (count / len(non_null)) * 100
                        bar = '#' * int(percent / 5)
                        # 截断过长的值
                        display_val = val[:40] + "..." if len(val) > 40 else val
                        report_lines.append(f"    {display_val}: {count} ({percent:.1f}%) {bar}")
        
        # 字典类型处理
        elif all(isinstance(v, dict) for v in values if v is not None):
            # 计算基本统计信息
            non_null_dicts = [v for v in values if v is not None]
            if non_null_dicts:
                report_lines.append(f"  - 字典字段平均数: {sum(len(v) for v in non_null_dicts)/len(non_null_dicts):.1f}")
                
                # 统计字典中的键
                all_dict_keys = set()
                key_counts = defaultdict(int)
                for v in non_null_dicts:
                    all_dict_keys.update(v.keys())
                    for k in v.keys():
                        key_counts[k] += 1
                
                if all_dict_keys:
                    # 按出现频率排序键
                    sorted_keys = sorted(key_counts.items(), key=lambda x: -x[1])
                    
                    if len(sorted_keys) > max_categories:
                        # 只显示最常见的几个键
                        top_keys = sorted_keys[:max_categories]
                        report_lines.append(f"  - 最常见字典键 (前{max_categories}个，共{len(all_dict_keys)}个):")
                        for key, count in top_keys:
                            percent = (count / len(non_null_dicts)) * 100
                            report_lines.append(f"    {key}: 出现在{count}个记录中 ({percent:.1f}%)")
                    else:
                        report_lines.append(f"  - 字典键集合 ({len(all_dict_keys)}个):")
                        for key, count in sorted_keys:
                            percent = (count / len(non_null_dicts)) * 100
                            report_lines.append(f"    {key}: 出现在{count}个记录中 ({percent:.1f}%)")
        
        # 列表类型处理
        elif all(isinstance(v, list) for v in values if v is not None):
            non_null_lists = [v for v in values if v is not None]
            if non_null_lists:
                list_lengths = [len(v) for v in non_null_lists]
                report_lines.append(f"  - 列表最短长度: {min(list_lengths)}")
                report_lines.append(f"  - 列表最长长度: {max(list_lengths)}")
                report_lines.append(f"  - 列表平均长度: {sum(list_lengths)/len(list_lengths):.1f}")
                
                # 如果列表元素较短，尝试分析其中的值
                if sum(list_lengths) < 1000:  # 避免分析太大的数据集
                    # 统计所有出现的元素
                    all_elements = []
                    for lst in non_null_lists:
                        all_elements.extend(lst)
                    
                    if all_elements:
                        # 检查元素类型
                        element_types = set(type(e).__name__ for e in all_elements if e is not None)
                        report_lines.append(f"  - 元素类型: {', '.join(element_types)}")
                        
                        # 如果元素是简单类型（字符串/数字），统计出现频率
                        if all(isinstance(e, (str, int, float)) for e in all_elements if e is not None):
                            element_counts = defaultdict(int)
                            for e in all_elements:
                                element_counts[e] += 1
                            
                            unique_elements = len(element_counts)
                            if unique_elements <= 30:
                                # 如果元素数量适中，显示统计
                                most_common = sorted(element_counts.items(), key=lambda x: -x[1])
                                
                                if len(most_common) > max_categories:
                                    # 只显示最常见的几个元素
                                    top_elements = most_common[:max_categories]
                                    report_lines.append(f"  - 元素分布 (显示前{max_categories}个，共{unique_elements}个不同值):")
                                    for val, count in top_elements:
                                        percent = (count / len(all_elements)) * 100
                                        # 处理字符串截断
                                        if isinstance(val, str) and len(val) > 30:
                                            val = val[:30] + "..."
                                        report_lines.append(f"    {val}: {count} ({percent:.1f}%)")
                                    
                                    other_count = sum(count for _, count in most_common[max_categories:])
                                    other_percent = (other_count / len(all_elements)) * 100
                                    report_lines.append(f"    其他({unique_elements - max_categories}个值): {other_count} ({other_percent:.1f}%)")
                                else:
                                    report_lines.append("  - 元素分布:")
                                    for val, count in most_common:
                                        percent = (count / len(all_elements)) * 100
                                        # 处理字符串截断
                                        if isinstance(val, str) and len(val) > 30:
                                            val = val[:30] + "..."
                                        report_lines.append(f"    {val}: {count} ({percent:.1f}%)")
                            else:
                                report_lines.append(f"  - 不同元素数量: {unique_elements} (太多，不显示详细分布)")

def analyze_data_file(
    file_path: str,
    output_file: Optional[str] = None,
    max_categories: int = 5,
    exclude_fields: List[str] = None,
    include_fields: List[str] = None,
    metadata_fields: List[str] = None
) -> str:
    """
    分析指定JSON文件中的数据
    
    Args:
        file_path: 要分析的JSON文件路径
        output_file: 输出报告的文件路径，不指定则只返回报告而不保存
        max_categories: 每个字段最多显示的类别数量
        exclude_fields: 要排除的字段列表
        include_fields: 要包含的字段列表(如果指定，则只分析这些字段)
        metadata_fields: 要视为元数据的字段(用于分组分析)
    
    Returns:
        格式化的分析报告文本
    """
    try:
        # 读取JSON文件
        print(f"正在读取文件: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 确保数据是列表格式
        if not isinstance(data, list):
            if isinstance(data, dict) and any(isinstance(data.get(k), list) for k in data):
                # 尝试找到数据列表
                for key in data:
                    if isinstance(data[key], list):
                        data = data[key]
                        print(f"从键 '{key}' 中提取数据列表")
                        break
            else:
                # 如果不是列表也不是包含列表的字典，将其包装成列表
                data = [data]
                print("将单个数据项包装为列表")
        
        print(f"读取到 {len(data)} 条数据记录")
        
        # 调用分析方法
        report = analyze_data(
            data, 
            max_categories=max_categories,
            exclude_fields=exclude_fields,
            include_fields=include_fields,
            metadata_fields=metadata_fields
        )
        
        # 如果指定了输出文件，则保存报告
        if output_file:
            # 确保输出目录存在
            output_dir = os.path.dirname(output_file)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"分析报告已保存到: {output_file}")
        
        return report
    
    except FileNotFoundError:
        error_msg = f"文件未找到: {file_path}"
        print(error_msg)
        return error_msg
    except json.JSONDecodeError:
        error_msg = f"JSON解析错误: {file_path} 不是有效的JSON文件"
        print(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"分析文件时出错: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return error_msg

def analyze_data_dir(
    dir_path: str, 
    pattern: str = "*.json",
    output_dir: Optional[str] = None,
    **kwargs
) -> Dict[str, str]:
    """
    分析指定目录下符合模式的所有数据文件
    
    Args:
        dir_path: 要分析的目录路径
        pattern: 文件匹配模式，默认为所有JSON文件
        output_dir: 输出报告的目录，不指定则使用原目录
        **kwargs: 传递给analyze_data_file的其他参数
    
    Returns:
        文件名到分析报告的映射字典
    """
    import glob
    
    # 确保目录路径存在
    if not os.path.isdir(dir_path):
        print(f"目录不存在: {dir_path}")
        return {}
    
    # 获取匹配的文件列表
    file_pattern = os.path.join(dir_path, pattern)
    files = glob.glob(file_pattern)
    
    if not files:
        print(f"在 {dir_path} 中没有找到匹配 '{pattern}' 的文件")
        return {}
    
    print(f"在 {dir_path} 中找到 {len(files)} 个匹配文件")
    
    # 设置输出目录
    if output_dir is None:
        output_dir = dir_path
    else:
        os.makedirs(output_dir, exist_ok=True)
    
    # 分析每个文件
    results = {}
    for file_path in files:
        file_name = os.path.basename(file_path)
        print(f"\n开始分析文件: {file_name}")
        
        # 设置输出报告路径
        report_name = f"report_{file_name.rsplit('.', 1)[0]}.txt"
        output_path = os.path.join(output_dir, report_name)
        
        # 分析文件
        report = analyze_data_file(
            file_path, 
            output_file=output_path,
            **kwargs
        )
        
        results[file_name] = report
    
    return results

def main():
    parser = argparse.ArgumentParser(description="分析数据文件")
    parser.add_argument("path", help="要分析的文件或目录路径")
    parser.add_argument("--output", "-o", help="输出报告的路径")
    parser.add_argument("--categories", "-c", type=int, default=5, help="每个字段显示的最大类别数")
    parser.add_argument("--metadata", "-m", nargs="+", help="要视为元数据的字段")
    parser.add_argument("--include", "-i", nargs="+", help="要包含的字段")
    parser.add_argument("--exclude", "-e", nargs="+", help="要排除的字段")
    parser.add_argument("--pattern", "-p", default="*.json", help="文件匹配模式")
    
    args = parser.parse_args()
    
    import os
    if os.path.isdir(args.path):
        analyze_data_dir(
            dir_path=args.path,
            pattern=args.pattern,
            output_dir=args.output,
            max_categories=args.categories,
            metadata_fields=args.metadata,
            include_fields=args.include,
            exclude_fields=args.exclude
        )
    else:
        report = analyze_data_file(
            file_path=args.path,
            output_file=args.output,
            max_categories=args.categories,
            metadata_fields=args.metadata,
            include_fields=args.include,
            exclude_fields=args.exclude
        )
        if not args.output:
            print(report)

if __name__ == "__main__":
    main()