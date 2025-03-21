import argparse
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from scripts.base_model import ModelConfig, BaseModel, TableGPT, create_base_parser, create_model_config
from typing import Optional

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

def show_ollama_guide(config: ModelConfig, quantization="q8_0"):
    """显示 Ollama 集成指南"""
    print("\n=== Ollama 集成（可选）===")
    model_path = config.cache_dir / f"tablegpt-7b-{quantization}.gguf"
    if not model_path.exists():
        print("✗ 请先完成模型量化")
        return False
        
    modelfile_path = config.cache_dir / "Modelfile"
    modelfile_content = f'''FROM {model_path.absolute()}
LICENSE Apache 2.0
TEMPLATE """
表格数据分析助手。请根据提供的表格数据回答问题。
请简洁直接地回答问题，回答完成后输出"<END>"表示结束。

{{{{.Prompt}}}}
"""

PARAMETER temperature {config.temperature}
PARAMETER top_p {config.top_p}
PARAMETER stop "<END>"'''

    print("1. 创建 Modelfile:")
    print(f"已创建 Modelfile 在: {modelfile_path}")
    modelfile_path.write_text(modelfile_content)
    
    print("\n2. 创建 Ollama 模型:")
    print(f"ollama create tablegpt -f {modelfile_path}")
    
    print("\n3. 测试模型:")
    print("ollama run tablegpt '分析这个表格的数据'")
    return True

class TableGPT(BaseModel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_df = None
        self.conversation_history = []
        self.max_history = 5

    def _find_quantized_model(self) -> Optional[str]:
        # 检查本地是否有量化版本
        local_path = Path("./models/tablegpt-7b-q8_0.gguf")
        if local_path.exists():
            return str(local_path)
        return None

    def _get_quantized_path(self) -> Path:
        return self.config.cache_dir / "model-f16.gguf"

    def _prepare_prompt(self, query: str, df=None, **kwargs) -> str:
        """准备带有对话历史的提示词"""
        if df is not None:
            self.current_df = df
            
        if self.current_df is None:
            raise ValueError("请先设置数据框")
            
        # 获取表格数据和统计信息
        table_data = self.current_df.head(10).to_string(index=False)
        stats_info = self.current_df.describe().round(2).to_string()
        
        # 格式化对话历史
        history = self._format_history()
        history_section = f"\n\n对话历史：\n{history}" if history else ""
        
        return f"""表格数据分析助手。请根据以下表格数据和统计信息，回答用户的问题。
请简洁直接地回答问题。

表格数据：
{table_data}

统计信息：
{stats_info}{history_section}

用户：{query}
助手："""

    def _generate_modelfile(self, model_path: str = None) -> str:
        """生成 Modelfile 内容"""
        return f'''FROM {model_path if model_path else self.model_name}
LICENSE Apache 2.0
TEMPLATE """
表格数据分析助手。请根据提供的表格数据回答问题。
请简洁直接地回答问题，回答完成后输出"<END>"表示结束。

{{{{.Prompt}}}}
"""

PARAMETER temperature {self.config.temperature}
PARAMETER top_p {self.config.top_p}
PARAMETER stop "<END>"'''

    def _show_special_commands(self):
        """显示特殊命令说明"""
        super()._show_special_commands()
        print("/clear 或 /c - 清除对话历史")
        print("/data - 显示当前数据概览")
        print("/stats - 显示数据统计信息")

    def _handle_special_command(self, command: str) -> bool:
        """处理特殊命令"""
        if super()._handle_special_command(command):
            return True
            
        if command.lower() == "/data":
            if self.current_df is not None:
                print("\n当前数据概览：")
                print(self.current_df.head().to_string())
            else:
                print("未设置数据")
            return True
            
        if command.lower() == "/stats":
            if self.current_df is not None:
                print("\n数据统计信息：")
                print(self.current_df.describe().round(2).to_string())
            else:
                print("未设置数据")
            return True
            
        return False

def main():
    # 创建解析器并添加特定参数
    parser = create_base_parser("TableGPT 表格分析助手")
    parser.add_argument('--test', action='store_true', help="测试已量化的模型")
    parser.add_argument('--rows', type=int, default=20, help="示例数据行数")
    parser.add_argument('--max_history', type=int, default=5, help="保留的最大对话轮数")
    args = parser.parse_args()
    
    # 设置默认值
    if not args.model_id:
        args.model_id = "tablegpt/TableGPT2-7B"
    
    # 创建模型配置
    config = create_model_config(args)
    config.max_history = args.max_history
    
    # 创建模型实例
    table_gpt = TableGPT(
        args.model_id,
        use_llama=(args.backend == 'llama'),
        use_ollama=(args.backend == 'ollama'),
        config=config
    )

    # 如果是测试模式，直接开始交互
    if args.test:
        print(f"\n生成示例数据（{args.rows}行）...")
        df = generate_sample_data(args.rows)
        table_gpt.current_df = df
        print("✓ 数据已加载")
        print("\n可用命令：")
        print("/data - 显示数据概览")
        print("/stats - 显示统计信息")
        print("/clear - 清除对话历史")
        table_gpt.interactive_session()
        return

    # 如果是 Ollama 模式，显示 Ollama 指南
    if args.backend == 'ollama':
        show_ollama_guide(config, args.quantization)
        return

if __name__ == "__main__":
    main()