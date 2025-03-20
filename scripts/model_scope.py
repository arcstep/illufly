import pandas as pd
from modelscope import AutoModelForCausalLM, AutoTokenizer
import numpy as np
from datetime import datetime, timedelta
from transformers import TextIteratorStreamer
import threading
import sys
import locale

def generate_sample_data(n_rows=50):
    """生成示例数据"""
    np.random.seed(42)
    
    departments = ['研发', '销售', '市场', '人力资源', '财务', '运营', '客服', '产品', '法务', '行政']
    cities = ['北京', '上海', '广州', '深圳', '杭州', '成都', '武汉', '西安', '南京', '重庆']
    levels = ['P4', 'P5', 'P6', 'P7', 'P8', 'M1', 'M2', 'M3']
    education = ['本科', '硕士', '博士', 'MBA', '大专']
    
    data = {
        '员工ID': [f'EMP{str(i).zfill(6)}' for i in range(1, n_rows + 1)],
        '部门': np.random.choice(departments, n_rows),
        '职级': np.random.choice(levels, n_rows, p=[0.3, 0.25, 0.2, 0.1, 0.05, 0.05, 0.03, 0.02]),
        '工作地点': np.random.choice(cities, n_rows),
        '基本工资': np.random.normal(20000, 5000, n_rows).astype(int),
        '年终奖金': np.random.exponential(30000, n_rows).astype(int),
        '入职日期': [(datetime(2018, 1, 1) + timedelta(days=int(x))).strftime('%Y-%m-%d') 
                  for x in np.random.uniform(0, 2000, n_rows)],
        '学历': np.random.choice(education, n_rows),
        '考评分数': np.random.normal(85, 10, n_rows).clip(60, 100).round(1),
        '项目完成数': np.random.poisson(8, n_rows)
    }
    
    df = pd.DataFrame(data)
    
    level_multiplier = {'P4': 1, 'P5': 1.2, 'P6': 1.5, 'P7': 2, 'P8': 2.5, 'M1': 3, 'M2': 4, 'M3': 5}
    df['基本工资'] = df.apply(lambda x: int(x['基本工资'] * level_multiplier[x['职级']]), axis=1)
    
    city_multiplier = {'北京': 1.2, '上海': 1.2, '广州': 1.1, '深圳': 1.1, '杭州': 1.05}
    df['基本工资'] = df.apply(lambda x: int(x['基本工资'] * city_multiplier.get(x['工作地点'], 1)), axis=1)
    
    return df

class TableGPT:
    def __init__(self, model_name="LLM-Research/TableGPT2-7B"):
        print("正在加载模型...")
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name, 
            torch_dtype="auto", 
            device_map="auto"
        )
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        print("模型加载完成！")
        
        self.prompt_template = """根据以下表格数据和统计信息，回答用户的问题。

/*
"{var_name}.head().to_string(index=False)" as follows:
{df_info}
*/

统计信息：
{stats_info}

例如：
user: 谁的薪资最高？
assistant: 根据数据显示，薪资最高的员工基本工资为xxx元。

不要根据表格数据自由发挥；
不要评论，不要废话，回答后立即停止，不要回答多余问题。

Question: {user_question}
"""
        
    def get_response(self, df, question):
        prompt = self.prompt_template.format(
            var_name="df",
            df_info=df.head(10).to_string(index=False),
            stats_info=df.describe().round(2).to_string(),
            user_question=question
        )
        
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ]
        text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        model_inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)

        print("\n回答: ", end="", flush=True)
        
        # 创建streamer
        streamer = TextIteratorStreamer(
            self.tokenizer,
            skip_special_tokens=True,
            skip_prompt=True
        )
        
        # 在新线程中运行模型生成
        generation_kwargs = dict(
            **model_inputs,
            max_new_tokens=512,
            temperature=0.7,
            top_p=0.95,
            do_sample=True,
            streamer=streamer,
        )
        
        thread = threading.Thread(target=self.model.generate, kwargs=generation_kwargs)
        thread.start()

        # 在主线程中处理输出流
        for new_text in streamer:
            print(new_text, end="", flush=True)
        print()  # 最后换行
    
    def interactive_session(self, df=None):
        # 设置标准输入输出的编码
        if sys.stdout.encoding != 'UTF-8':
            sys.stdout.reconfigure(encoding='UTF-8')
        if sys.stdin.encoding != 'UTF-8':
            sys.stdin.reconfigure(encoding='UTF-8')
        
        if df is None:
            df = generate_sample_data(50)
            
        print("\n=== 数据概览 ===")
        print("\n数据形状:", df.shape)
        print("\n列名称:", list(df.columns))
        print("\n数据类型:")
        print(df.dtypes)
        print("\n基本统计信息:")
        print(df.describe().round(2))
        print("\n数据预览（前5行）:")
        print(df.head().to_string(index=False))
        
        print("\n=== 开始交互式问答 ===")
        print("输入 q、exit 或 quit 退出")
        print("支持的特殊命令：")
        print("- filter <条件>: 根据条件筛选数据，例如 'filter 基本工资>30000'")
        print("- sample <数量>: 随机抽样显示数据，例如 'sample 100'")
        
        current_df = df
        
        while True:
            try:
                question = input("\n请输入问题: ").strip()
            except UnicodeDecodeError:
                print("\n✗ 输入编码错误，请重试")
                continue
            except EOFError:
                print("\n会话结束")
                break
            except KeyboardInterrupt:
                print("\n会话被用户中断")
                break
            
            if question.lower() in ['q', 'exit', 'quit']:
                print("退出交互式测试")
                break
                
            if not question:
                continue
            
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
            
            print("生成回答中...")
            try:
                self.get_response(current_df, question)
            except Exception as e:
                print(f"\n✗ 生成回答失败: {str(e)}")

# 使用示例
if __name__ == "__main__":
    # 初始化模型
    gpt = TableGPT()
    
    # 启动交互式会话
    gpt.interactive_session()