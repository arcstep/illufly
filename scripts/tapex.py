import os
import pandas as pd
import torch
from torch.utils.data import Dataset
from transformers import (
    TapexTokenizer,
    BartForConditionalGeneration,
    Seq2SeqTrainingArguments,
    Seq2SeqTrainer,
    DataCollatorForSeq2Seq,
    BartTokenizer
)
import argparse
import logging
import numpy as np
from sklearn.model_selection import train_test_split

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TableQADataset(Dataset):
    """表格问答数据集"""
    
    def __init__(self, data, tokenizer, max_length=512, target_max_length=64):
        self.data = data
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.target_max_length = target_max_length
        # 创建一个空表格，用于编码答案
        self.empty_table = pd.DataFrame({"text": [""]})
    
    def __len__(self):
        return len(self.data)
    
    def __getitem__(self, idx):
        item = self.data[idx]
        question = item["question"]
        table = item["table"].copy()
        answer = item["answer"]
        
        # 确保表格中的所有值都是字符串类型
        for col in table.columns:
            table[col] = table[col].astype(str)
        
        # 编码输入部分
        encoding = self.tokenizer(
            table=table, 
            query=question,
            padding="max_length",
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt"
        )
        
        # 关键修改：必须同时传递表格和查询
        # 使用空表格和答案作为查询来编码答案
        target_encoding = self.tokenizer(
            table=self.empty_table,  # 使用空表格
            query=answer,    # 答案作为查询
            padding="max_length",
            truncation=True,
            max_length=self.target_max_length,
            return_tensors="pt"
        )
        
        # 移除批次维度
        encoding = {k: v.squeeze(0) for k, v in encoding.items()}
        labels = target_encoding["input_ids"].squeeze(0)
        
        # 将填充标记替换为-100
        labels[labels == self.tokenizer.pad_token_id] = -100
        
        # 添加标签
        encoding["labels"] = labels
        
        return encoding

def create_demo_data():
    """创建更多中文表格问答样本用于训练"""
    data = []
    
    # 表格1: 员工信息
    table1 = pd.DataFrame({
        '姓名': ['张三', '李四', '王五', '赵六', '钱七', '孙八'],
        '年龄': [28, 35, 42, 31, 25, 39],
        '职位': ['工程师', '经理', '总监', '销售', '设计师', '顾问'],
        '薪资': [12000, 20000, 35000, 15000, 13000, 25000],
        '部门': ['技术', '管理', '管理', '市场', '技术', '咨询']
    })
    
    # 表格1的问答对 - 大幅增加样本多样性
    qa_pairs1 = [
        # 查找类问题
        ("谁的薪资最高？", "王五"),
        ("张三是什么职位？", "工程师"),
        ("李四在哪个部门工作？", "管理"),
        ("谁的年龄最小？", "钱七"),
        ("谁的年龄最大？", "王五"),
        ("销售的姓名是？", "赵六"),
        ("管理部门有几个人？", "2"),
        
        # 比较类问题
        ("张三和李四谁的薪资更高？", "李四"),
        ("技术部门中谁的薪资更高？", "张三"),
        ("王五比李四大多少岁？", "7"),
        
        # 计算类问题
        ("所有员工的平均薪资是多少？", "20000"),
        ("技术部门的平均薪资是多少？", "12500"),
        ("所有员工的薪资总和是多少？", "120000"),
        ("管理部门的平均年龄是多少？", "38.5"),
    ]
    
    # 表格2: 销售数据
    table2 = pd.DataFrame({
        '产品': ['手机A', '手机B', '平板C', '电脑D', '耳机E', '手表F'],
        '价格': [3999, 5999, 2999, 8999, 999, 1999],
        '销量': [1500, 800, 1200, 300, 2000, 1000],
        '评分': [4.5, 4.8, 4.2, 4.7, 4.3, 4.6],
        '上市日期': ['2023-01', '2023-03', '2022-11', '2023-02', '2022-09', '2023-05']
    })
    
    # 表格2的问答对
    qa_pairs2 = [
        # 查找类问题
        ("销量最高的是什么产品？", "耳机E"),
        ("手机A的售价是多少？", "3999"),
        ("评分最高的产品是什么？", "手机B"),
        ("最便宜的产品是什么？", "耳机E"),
        ("最贵的产品是什么？", "电脑D"),
        ("哪个产品最早上市？", "耳机E"),
        ("最近上市的产品是哪个？", "手表F"),
        
        # 比较类问题
        ("手机A和手机B哪个销量更高？", "手机A"),
        ("平板C和耳机E的价格差多少？", "2000"),
        ("手表F比耳机E贵多少？", "1000"),
        
        # 计算类问题
        ("所有产品的平均价格是多少？", "4166"),
        ("手机类产品的平均销量是多少？", "1150"),
        ("评分超过4.5的产品有几个？", "3"),
        ("2023年上市的产品有几个？", "5"),
    ]
    
    # 表格3: 学生成绩
    table3 = pd.DataFrame({
        '学生': ['小明', '小红', '小张', '小李', '小王', '小陈'],
        '语文': [85, 92, 78, 90, 65, 88],
        '数学': [92, 78, 85, 95, 72, 67],
        '英语': [78, 94, 80, 85, 68, 92],
        '班级': ['一班', '二班', '一班', '三班', '二班', '三班']
    })
    
    # 表格3的问答对
    qa_pairs3 = [
        # 查找类问题
        ("谁的语文成绩最高？", "小红"),
        ("小明的数学成绩是多少？", "92"),
        ("数学成绩最高的是谁？", "小李"),
        ("小张在哪个班级？", "一班"),
        ("三班有几个学生？", "2"),
        
        # 比较类问题
        ("小明和小红谁的数学成绩更高？", "小明"),
        ("一班和二班哪个班级的英语平均分更高？", "二班"),
        ("小陈的英语比语文高多少分？", "4"),
        
        # 计算类问题
        ("小李的总分是多少？", "270"),
        ("一班的数学平均分是多少？", "88.5"),
        ("所有学生的英语平均分是多少？", "82.8"),
        ("二班的平均总分是多少？", "232.5"),
    ]
    
    # 将所有QA对添加到数据集
    for table, qa_pairs in [(table1, qa_pairs1), (table2, qa_pairs2), (table3, qa_pairs3)]:
        for question, answer in qa_pairs:
            data.append({
                "question": question,
                "table": table.copy(),
                "answer": answer
            })
    
    return data

# 自定义数据收集器，处理张量创建效率问题
class CustomDataCollator(DataCollatorForSeq2Seq):
    def __call__(self, features, return_tensors=None):
        # 转换特征为单一numpy数组
        for key in features[0].keys():
            if isinstance(features[0][key], (list, np.ndarray)):
                # 先转换为numpy数组再创建张量
                features_key = [feature[key] for feature in features]
                array = np.array(features_key)
                for i, feature in enumerate(features):
                    feature[key] = array[i]
        
        # 调用父类方法
        return super().__call__(features, return_tensors)

def train_model(args):
    """训练模型"""
    # 加载表格问答数据
    data = create_demo_data()
    print(f"创建了 {len(data)} 条训练样本")
    
    # 分割训练集和验证集
    train_data, val_data = train_test_split(data, test_size=0.2, random_state=42)
    
    # 初始化分词器和模型
    tokenizer = TapexTokenizer.from_pretrained(args.model_path)
    model = BartForConditionalGeneration.from_pretrained(args.model_path)
    
    # 定义编码函数
    def encode_data(examples):
        inputs = []
        for example in examples:
            # 确保表格中的所有值都是字符串类型
            table = example["table"].copy()
            for col in table.columns:
                table[col] = table[col].astype(str)
            inputs.append({"table": table, "question": example["question"], "answer": example["answer"]})
        return inputs
    
    # 编码数据
    train_encodings = encode_data(train_data)
    val_encodings = encode_data(val_data)
    
    # 定义数据集类
    class TableQADataset(Dataset):
        def __init__(self, encodings, tokenizer):
            self.encodings = encodings
            self.tokenizer = tokenizer
            # 创建一个空表格，用于编码答案
            self.empty_table = pd.DataFrame({"text": [""]})
        
        def __len__(self):
            return len(self.encodings)
        
        def __getitem__(self, idx):
            item = self.encodings[idx]
            
            # 编码输入
            model_inputs = self.tokenizer(
                table=item["table"],
                query=item["question"],
                padding="max_length",
                truncation=True,
                max_length=512,
                return_tensors="pt"
            )
            
            # 关键修改：必须同时传递表格和查询
            # 使用空表格和答案作为查询来编码答案
            answer_encoding = self.tokenizer(
                table=self.empty_table,  # 使用空表格
                query=item["answer"],    # 答案作为查询
                padding="max_length",
                truncation=True,
                max_length=64,
                return_tensors="pt"
            )
            
            # 设置标签
            model_inputs = {k: v.squeeze(0) for k, v in model_inputs.items()}
            model_inputs["labels"] = answer_encoding["input_ids"].squeeze(0)
            model_inputs["labels"][model_inputs["labels"] == self.tokenizer.pad_token_id] = -100
            
            return model_inputs
    
    # 创建数据集
    train_dataset = TableQADataset(train_encodings, tokenizer)
    val_dataset = TableQADataset(val_encodings, tokenizer)
    
    # 训练参数
    training_args = Seq2SeqTrainingArguments(
        output_dir=args.output_dir,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        eval_strategy="no",  # 修正参数名
        save_strategy="epoch",
        num_train_epochs=args.epochs,
        learning_rate=args.learning_rate,
        weight_decay=0.01,
        save_total_limit=3,
        predict_with_generate=False,
        logging_dir=os.path.join(args.output_dir, "logs"),
        logging_steps=10,
        fp16=False,
        dataloader_num_workers=0
    )
    
    # 使用标准收集器
    data_collator = DataCollatorForSeq2Seq(
        tokenizer=tokenizer, 
        model=model,
        padding=True
    )
    
    # 创建训练器
    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        data_collator=data_collator
    )
    
    # 开始训练
    print("开始训练模型...")
    trainer.train()
    
    # 保存模型和分词器
    print(f"保存模型到 {args.output_dir}")
    model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

def predict(args):
    """使用模型进行预测"""
    # 加载模型和分词器
    tokenizer = TapexTokenizer.from_pretrained(args.model_path)
    model = BartForConditionalGeneration.from_pretrained(args.model_path)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    
    # 测试表格
    test_table = pd.DataFrame({
        '姓名': ['张三', '李四', '王五'],
        '年龄': [25, 30, 35],
        '职业': ['工程师', '医生', '教师'],
        '薪资': [15000, 20000, 12000]
    })
    
    # 确保表格中的所有值都是字符串类型
    for col in test_table.columns:
        test_table[col] = test_table[col].astype(str)
    
    # 测试问题
    test_question = "谁的薪资最高？"
    
    # 编码输入
    inputs = tokenizer(
        table=test_table,
        query=test_question,
        return_tensors="pt",
        padding="max_length",
        truncation=True,
        max_length=512
    ).to(device)
    
    # 生成答案
    with torch.no_grad():
        outputs = model.generate(
            inputs["input_ids"],
            attention_mask=inputs["attention_mask"],
            max_length=64,
            num_beams=4,           # 使用束搜索
            early_stopping=True,   # 提前停止生成
            no_repeat_ngram_size=2 # 避免重复
        )
    
    # 解码答案
    answer = tokenizer.decode(outputs[0], skip_special_tokens=True)
    print(f"问题: {test_question}")
    print(f"答案: {answer}")
    
    # 交互式测试
    print("\n开始交互式测试 (输入'q'退出):")
    print("当前使用的表格数据:")
    print(test_table)
    print("-" * 40)
    
    while True:
        question = input("请输入问题: ")
        if question.lower() in ["q", "quit", "exit"]:
            break
            
        inputs = tokenizer(
            table=test_table,
            query=question,
            return_tensors="pt",
            padding="max_length",
            truncation=True,
            max_length=512
        ).to(device)
        
        with torch.no_grad():
            outputs = model.generate(
                inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
                max_length=64,
                num_beams=4,           # 使用束搜索
                early_stopping=True,   # 提前停止生成
                no_repeat_ngram_size=2 # 避免重复
            )
        
        answer = tokenizer.decode(outputs[0], skip_special_tokens=True)
        print(f"答案: {answer}")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="TAPEX表格问答模型")
    parser.add_argument("--train", action="store_true", help="是否进行模型训练")
    parser.add_argument("--model_path", type=str, default="microsoft/tapex-base", 
                        help="预训练模型路径或训练后的模型路径")
    parser.add_argument("--output_dir", type=str, default="./tapex-chinese-demo",
                        help="模型输出路径")
    parser.add_argument("--batch_size", type=int, default=4, help="训练批次大小")
    parser.add_argument("--epochs", type=int, default=10, help="训练轮数")
    parser.add_argument("--learning_rate", type=float, default=2e-5, help="学习率")
    
    args = parser.parse_args()
    
    # 创建输出目录
    os.makedirs(args.output_dir, exist_ok=True)
    
    # 根据参数选择操作
    if args.train:
        train_model(args)
    
    # 始终进行预测测试
    predict(args)

if __name__ == "__main__":
    main()