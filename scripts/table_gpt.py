import os
from pathlib import Path
import argparse
from huggingface_hub import try_to_load_from_cache
from transformers.utils import WEIGHTS_NAME, CONFIG_NAME
from llama_cpp import Llama
import pandas as pd
import json
import sys
import numpy as np
from datetime import datetime, timedelta

def show_model_path(model_id):
    """显示模型路径信息"""
    print("\n=== 步骤1: 查找模型路径 ===")
    
    # 尝试找到配置文件
    config_path = try_to_load_from_cache(model_id, CONFIG_NAME)
    if config_path:
        model_path = Path(config_path).parent
        print(f"✓ 已找到缓存模型: {model_path}")
        return model_path
    
    # 尝试在默认缓存目录中查找
    cache_dir = Path.home() / ".cache/huggingface/hub"
    if cache_dir.exists():
        model_id_path = model_id.replace('/', '--')
        for path in cache_dir.glob(f"**/{model_id_path}*/pytorch_model.bin"):
            print(f"✓ 已找到缓存模型: {path.parent}")
            return path.parent
    
    print("✗ 未找到缓存模型，请先下载：")
    print(f"huggingface-cli download {model_id}")
    return None

def show_llama_cpp_guide():
    """显示llama.cpp相关指南"""
    print("\n=== 步骤2: 准备llama.cpp ===")
    if Path("./llama.cpp").exists():
        print("✓ 已找到llama.cpp目录")
        if Path("./llama.cpp/build/bin/llama-quantize").exists():
            print("✓ 已编译llama.cpp")
            return True
        else:
            print("请使用CMake编译llama.cpp:")
            print("cd llama.cpp")
            print("cmake -B build")
            print("cmake --build build --config Release")
            print("\n编译完成后，请重新运行此脚本继续后续步骤")
            return False
    else:
        print("请克隆llama.cpp:")
        print("git clone https://github.com/ggerganov/llama.cpp.git")
        print("\n然后使用CMake编译:")
        print("cd llama.cpp")
        print("cmake -B build")
        print("cmake --build build --config Release")
        print("\n编译完成后，请重新运行此脚本继续后续步骤")
        return False

def show_conversion_guide(model_path=None):
    """显示转换指南"""
    print("\n=== 步骤3: 转换为GGUF格式 ===")
    if model_path:
        if Path("./models/model-f16.gguf").exists():
            print("✓ 已完成GGUF格式转换")
            return True
        else:
            cmd = f"python llama.cpp/convert_hf_to_gguf.py* --outfile ./models/model-f16.gguf --outtype f16 {model_path}"
            print("执行转换命令:")
            print(cmd)
            print("\n转换完成后，请重新运行此脚本继续后续步骤")
            return False
    return False

def show_quantization_guide(quantization="q4_0"):
    """显示量化指南"""
    print(f"\n=== 步骤4: {quantization}量化 ===")
    model_path = Path(f"./models/tablegpt-7b-{quantization}.gguf")
    if model_path.exists():
        print("✓ 已完成量化")
        print("\n=== 使用指南 ===")
        print("1. 测试模型:")
        print(f"   python {Path(__file__).name} --test")
        print("\n2. 在代码中使用:")
        print("```python")
        print("from llama_cpp import Llama")
        print("model = Llama(")
        print(f"    model_path='{model_path}',")
        print("    n_ctx=4096,      # 上下文窗口大小")
        print("    n_threads=6,      # CPU线程数")
        print("    n_batch=512      # 批处理大小")
        print(")")
        print("# 生成回答")
        print('response = model.create_completion("你的问题", max_tokens=512)')
        print("print(response['choices'][0]['text'])")
        print("```")
        return True
    else:
        print("执行量化命令:")
        print(f"./llama.cpp/build/bin/llama-quantize ./models/model-f16.gguf ./models/tablegpt-7b-{quantization}.gguf {quantization}")
        print("\n量化完成后，请重新运行此脚本继续后续步骤")
        return False

def check_quantized_model(quantization="q4_0"):
    """检查量化模型是否存在"""
    model_path = Path("./models") / f"tablegpt-7b-{quantization}.gguf"
    if model_path.exists():
        print(f"\n✓ 已找到量化模型: {model_path}")
        return True
    return False

def generate_sample_data(n_rows=1000):
    """生成示例数据"""
    # 生成基础数据
    np.random.seed(42)  # 保证可重复性
    
    # 公司部门
    departments = ['研发', '销售', '市场', '人力资源', '财务', '运营', '客服', '产品', '法务', '行政']
    # 城市
    cities = ['北京', '上海', '广州', '深圳', '杭州', '成都', '武汉', '西安', '南京', '重庆']
    # 职级
    levels = ['P4', 'P5', 'P6', 'P7', 'P8', 'M1', 'M2', 'M3']
    # 学历
    education = ['本科', '硕士', '博士', 'MBA', '大专']
    
    # 生成数据
    data = {
        '员工ID': [f'EMP{str(i).zfill(6)}' for i in range(1, n_rows + 1)],
        '部门': np.random.choice(departments, n_rows),
        '职级': np.random.choice(levels, n_rows, p=[0.3, 0.25, 0.2, 0.1, 0.05, 0.05, 0.03, 0.02]),  # 使用概率分布
        '工作地点': np.random.choice(cities, n_rows),
        '基本工资': np.random.normal(20000, 5000, n_rows).astype(int),  # 正态分布
        '年终奖金': np.random.exponential(30000, n_rows).astype(int),  # 指数分布
        '入职日期': [(datetime(2018, 1, 1) + timedelta(days=int(x))).strftime('%Y-%m-%d') 
                  for x in np.random.uniform(0, 2000, n_rows)],
        '学历': np.random.choice(education, n_rows),
        '考评分数': np.random.normal(85, 10, n_rows).clip(60, 100).round(1),  # 正态分布，限制在60-100之间
        '项目完成数': np.random.poisson(8, n_rows)  # 泊松分布
    }
    
    df = pd.DataFrame(data)
    
    # 添加一些数据处理
    # 1. 基于职级调整工资
    level_multiplier = {'P4': 1, 'P5': 1.2, 'P6': 1.5, 'P7': 2, 'P8': 2.5, 'M1': 3, 'M2': 4, 'M3': 5}
    df['基本工资'] = df.apply(lambda x: int(x['基本工资'] * level_multiplier[x['职级']]), axis=1)
    
    # 2. 根据城市调整工资
    city_multiplier = {'北京': 1.2, '上海': 1.2, '广州': 1.1, '深圳': 1.1, '杭州': 1.05}
    df['基本工资'] = df.apply(lambda x: int(x['基本工资'] * city_multiplier.get(x['工作地点'], 1)), axis=1)
    
    return df

def interactive_test(use_ollama=False):
    """交互式测试模型"""
    print("\n=== 交互式测试模型 ===")
    
    # 使用新的示例数据
    df = generate_sample_data(50)
    
    # 打印数据信息
    print("\n=== 数据概览 ===")
    print("\n数据形状:", df.shape)
    print("\n列名称:", list(df.columns))
    print("\n数据类型:")
    print(df.dtypes)
    print("\n基本统计信息:")
    print(df.describe().round(2))
    print("\n数据预览（前5行）:")
    print(df.head().to_string(index=False))
    
    # 准备模型
    if not use_ollama:
        try:
            model = Llama(
                model_path=str(Path("./models/tablegpt-7b-q8_0.gguf")),
                n_ctx=4096,
                n_threads=6,
                n_batch=512
            )
        except Exception as e:
            print(f"\n✗ 模型加载失败: {str(e)}")
            return
    
    print("\n=== 开始交互式问答 ===")
    print("输入 q、exit 或 quit 退出")
    print("支持的特殊命令：")
    print("- filter <条件>: 根据条件筛选数据，例如 'filter 基本工资>30000'")
    print("- sample <数量>: 随机抽样显示数据，例如 'sample 100'")
    
    current_df = df  # 当前使用的数据框
    
    while True:
        question = input("\n请输入问题: ").strip()
        
        if question.lower() in ['q', 'exit', 'quit']:
            print("退出交互式测试")
            break
            
        if not question:
            continue
        
        # 处理特殊命令
        if question.startswith('filter '):
            try:
                condition = question[7:]
                current_df = df.query(condition)
                print(f"\n已筛选数据，当前数据量: {len(current_df)} 行")
                print("\n数据预览（前5行）:")
                print(current_df.head().to_string(index=False))
                continue
            except Exception as e:
                print(f"\n✗ 筛选条件错误: {str(e)}")
                continue
                
        if question.startswith('sample '):
            try:
                n = int(question[7:])
                current_df = df.sample(n=min(n, len(df)))
                print(f"\n已随机抽样，当前数据量: {len(current_df)} 行")
                print("\n数据预览（前5行）:")
                print(current_df.head().to_string(index=False))
                continue
            except Exception as e:
                print(f"\n✗ 抽样参数错误: {str(e)}")
                continue
            
        # 准备 prompt（使用当前数据框）
        if use_ollama:
            table_data = current_df.head(10).to_string(index=False)  # 只使用前50行
            stats_info = current_df.describe().round(2).to_string()
            prompt = f"""表格数据（展示前50行，总计{len(current_df)}行）如下：
{table_data}

数据统计信息：
{stats_info}

请回答以下问题，回答后请输出"<END>"：
{question}"""
        else:
            table_data = current_df.head(50).to_string(index=False)  # 只使用前50行
            stats_info = current_df.describe().round(2).to_string()
            prompt = f"""根据以下表格数据（展示前50行，总计{len(current_df)}行）和统计信息，回答用户的问题。

表格数据：
{table_data}

统计信息：
{stats_info}

不要根据表格数据自由发挥；
不要评论，不要废话，回答后立即停止，不要回答多余问题。

问题是：
{question}
"""
        
        print("生成回答中...")
        try:
            if use_ollama:
                import requests
                import sys
                
                print("\n回答: ", end="", flush=True)
                response = requests.post(
                    'http://localhost:11434/api/generate',
                    json={
                        "model": "tablegpt",
                        "prompt": prompt,
                        "stream": True,
                        "stop": ["<END>"]  # 添加停止词
                    },
                    stream=True
                )
                
                if response.status_code == 200:
                    for line in response.iter_lines():
                        if line:
                            chunk = json.loads(line)
                            if chunk.get('done', False):
                                print()  # 完成时换行
                                break
                            if "<END>" not in chunk['response']:  # 不显示 END 标记
                                sys.stdout.write(chunk['response'])
                                sys.stdout.flush()
                else:
                    print(f"\n✗ Ollama API 调用失败: {response.status_code}")
                    print(f"错误信息: {response.text}")
            else:
                # llama.cpp 的流式输出
                response = model.create_completion(
                    prompt,
                    max_tokens=512,
                    temperature=0.7,
                    top_p=0.95,
                    stream=True  # 启用流式输出
                )
                
                print("\n回答: ", end="", flush=True)
                for chunk in response:
                    chunk_text = chunk['choices'][0]['text']
                    sys.stdout.write(chunk_text)
                    sys.stdout.flush()
                print()  # 完成时换行
                
        except Exception as e:
            print(f"\n✗ 生成回答失败: {str(e)}")

def test_model(model_path):
    """测试模型"""
    print("\n=== 测试模型 ===")
    interactive_test(use_ollama=False)

def test_model_ollama():
    """使用 Ollama 测试模型"""
    print("\n=== 使用 Ollama 测试模型 ===")
    interactive_test(use_ollama=True)

def show_ollama_guide(quantization="q4_0"):
    """显示 Ollama 集成指南"""
    print("\n=== 步骤5: Ollama 集成（可选）===")
    model_path = Path(f"./models/tablegpt-7b-{quantization}.gguf")
    if not model_path.exists():
        print("✗ 请先完成模型量化")
        return False
        
    # 创建 Modelfile
    modelfile_path = Path("./models/Modelfile")
    modelfile_content = f'''FROM {model_path.absolute()}
LICENSE Apache 2.0
TEMPLATE """
表格数据分析助手。请根据提供的表格数据回答问题。
请简洁直接地回答问题，回答完成后输出"<END>"表示结束。

{{{{.Prompt}}}}
"""

PARAMETER temperature 0.7
PARAMETER top_p 0.7
PARAMETER stop "<END>"'''  # 添加停止词

    print("1. 创建 Modelfile:")
    print(f"已创建 Modelfile 在: {modelfile_path}")
    modelfile_path.write_text(modelfile_content)
    
    print("\n2. 创建 Ollama 模型:")
    print(f"ollama create tablegpt -f {modelfile_path}")
    
    print("\n3. 测试模型:")
    print("ollama run tablegpt '分析这个表格的数据'")
    return True

def main():
    parser = argparse.ArgumentParser(description="TableGPT模型转换和量化指南")
    parser.add_argument('--model_id', default="tablegpt/TableGPT2-7B", help="模型ID")
    parser.add_argument('--quantization', default="q4_0", help="量化类型")
    parser.add_argument('--test', action='store_true', help="测试已量化的模型")
    parser.add_argument('--ollama', action='store_true', help="使用 Ollama 进行测试")
    args = parser.parse_args()
    
    # 创建必要的目录
    Path("./models").mkdir(exist_ok=True)
    
    if args.test:
        if args.ollama:
            test_model_ollama()
        else:
            model_path = Path("./models") / f"tablegpt-7b-{args.quantization}.gguf"
            if model_path.exists():
                test_model(model_path)
            else:
                print(f"\n✗ 未找到量化模型: {model_path}")
        return
    
    # 步骤1: 检查模型路径
    model_path = show_model_path(args.model_id)
    if not model_path:
        print("\n请先下载模型后再继续")
        return
        
    # 步骤2: 检查llama.cpp
    if not show_llama_cpp_guide():
        return
        
    # 步骤3: 检查GGUF转换
    if not show_conversion_guide(model_path):
        return
        
    # 步骤4: 量化
    if not show_quantization_guide(args.quantization):
        return
        
    # 步骤5: Ollama 集成（可选）
    show_ollama_guide(args.quantization)

if __name__ == "__main__":
    main()