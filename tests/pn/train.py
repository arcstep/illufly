"""
策略网络训练数据生成器
用于生成模拟用户查询及其相应的动作分类数据
"""

from datetime import datetime
from typing import List, Dict, Any, Optional
from tqdm import tqdm

import asyncio
import json
import os
import random
import time
import argparse
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn.functional as F
import re
import matplotlib as mpl
import platform
from collections import defaultdict
from torch.utils.data import DataLoader
from transformers import get_cosine_schedule_with_warmup

# 导入您的OpenAI封装
from illufly.community.models import EmbeddingText
from illufly.community.models import BlockType
from illufly.community.openai import ChatOpenAI, OpenAIEmbeddings
from illufly.memory.pn import PolicyNetwork
from illufly.prompt import PromptTemplate
from illufly.rocksdb import IndexedRocksDB

# 统一日志队列初始化
import logging
from logging.handlers import QueueHandler, QueueListener
from queue import Queue
log_queue = Queue()
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 异步日志处理器
queue_handler = QueueHandler(log_queue)
logger.addHandler(queue_handler)


MODEL_PATH = "./tests/pn/models"
DATA_PATH = "./tests/pn/data"
EMBEDDING_PATH = "./tests/pn/embeddings"

# 定义动作空间常量
ACTION_DIRECT_DIALOGUE = 0
ACTION_QUERY_KNOWLEDGE = 1
ACTION_QUERY_DATABASE = 2

# 修改DOMAIN_MAP结构
DOMAIN_MAP = {
    # 动作类型定义
    'action_types': {
        0: {'zh': '直接对话', 'en': 'Direct Chat'},
        1: {'zh': '查询知识库', 'en': 'KnowledgeQuery'},
        2: {'zh': '查询数据库', 'en': 'DatabaseQuery'},
    },
    # 业务领域定义
    'domains': {
        'sales': {'zh': '售前咨询', 'en': 'Sales'},
        'linux': {'zh': 'Linux运维', 'en': 'Linux'},
        'documents': {'zh': '文档和会议', 'en': 'Documents'}
    }
}

# 生成辅助结构
ACTION_NAMES = {
    k: v['zh'] 
    for k, v in DOMAIN_MAP['action_types'].items()
}

DOMAINS = list(DOMAIN_MAP['domains'].keys())

# 设置中英双语显示
USE_CHINESE = True  # 可根据需要切换为False使用纯英文

# 配置字体
try:
    if USE_CHINESE:
        if platform.system() == 'Darwin':  # macOS
            mpl.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'Heiti TC', 'Songti SC']
        elif platform.system() == 'Windows':
            mpl.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
        else:  # Linux
            mpl.rcParams['font.sans-serif'] = ['WenQuanYi Zen Hei', 'Noto Sans CJK SC']
        mpl.rcParams['axes.unicode_minus'] = False
    else:
        mpl.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial']
except:
    print("Warning: Font configuration failed, using default fonts")
    USE_CHINESE = False

# 中英文字典
LABELS = {
    'action_distribution': ('Action Distribution', '动作类型分布'),
    'domain_distribution': ('Domain Distribution', '领域分布'),
    'query_length': ('Query Length Statistics', '查询长度统计'),
    'overall_stats': ('Overall Statistics', '总体统计'),
    'epoch': ('Epoch', '训练轮次'),
    'loss': ('Loss', '损失值'),
    'training_loss': ('Training Loss', '训练损失曲线'),
    'min_length': ('Min Length', '最短查询'),
    'max_length': ('Max Length', '最长查询'),
    'avg_length': ('Avg Length', '平均长度'),
    'total_samples': ('Total Samples', '总样本数'),
    'generate_time': ('Generation Time', '生成时间')
}

def to_tensor(data, device=None):
    """通用数据转换工具"""
    if isinstance(data, torch.Tensor):
        tensor = data
    elif isinstance(data, (list, tuple)):
        tensor = torch.tensor(data)
    elif isinstance(data, np.ndarray):
        tensor = torch.from_numpy(data)
    else:
        raise TypeError(f"不支持的数据类型: {type(data)}")
    
    return tensor.to(device) if device else tensor

def get_label(key):
    return LABELS[key][0] if not USE_CHINESE else LABELS[key][1]

class ActionSpaceConfig:
    """可扩展的动作空间配置"""
    
    def __init__(self):
        # 核心动作定义（类型: 显示名称）
        self.actions = DOMAIN_MAP['action_types']

        # 业务领域定义（名称: 中文标识）
        self.domains = DOMAIN_MAP['domains']
    
    @property
    def action_count(self):
        return len(self.actions)
    
    def get_action_name(self, action_id: int, chinese: bool = True) -> str:
        """获取动作名称"""
        name = self.actions.get(action_id)
        if not name:
            raise ValueError(f"无效动作ID: {action_id}")
        return name.get('zh') if chinese else name.get('en')
    
    def get_domain_name(self, domain: str, chinese: bool = True) -> str:
        """获取领域名称"""
        domain = self.domains.get(domain)
        if not domain:
            raise ValueError(f"无效领域: {domain}")
        return domain.get('zh') if chinese else domain.get('en')
    
    def validate_action(self, action_id: int) -> bool:
        return int(action_id) in self.actions  # 确保类型一致
    
    def get_all_domains(self, chinese: bool = True) -> List[str]:
        """获取所有业务领域"""
        return list(self.domains.keys() if chinese else self.domains.values())

# 初始化全局配置
action_config = ActionSpaceConfig()

class TrainingDataGenerator:
    """策略网络训练数据生成器"""
    
    def __init__(
        self, 
        output_dir: str = DATA_PATH,
        model: str = "gpt-4o-mini",
        imitator: Optional[str] = None,
        batch_size: int = 5,
        temperature: float = 0.7
    ):
        self.output_dir = output_dir
        self.batch_size = batch_size
        
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 初始化LLM客户端
        self.llm = ChatOpenAI(
            model=model,
            imitator=imitator
        )
        self.temperature = temperature
        
        # 定义提示模板
        self.system_prompt = """
        你是一个帮助生成策略网络训练数据的助手。你需要生成用户查询样本及其对应的动作分类。
        
        对于每个用户查询，你需要确定最合适的处理方式：
        1. 直接对话：适用于无需额外查询的一般性问题，如闲聊、意见请求等
        2. 查询知识库：适用于需要事实性知识的问题，如"什么是量子力学"、"北京有哪些景点"等
        3. 查询数据库：适用于需要特定用户或系统数据的问题，如"我的账户余额是多少"、"订单12345的状态"等
        
        对于数据库查询，还需要生成一个合理的SQL查询语句。
        """
        
        self.generation_prompt = """
        请针对{{domain}}领域，生成{{count}}个多样化的用户问题样本。
        
        对于每个样本，请提供以下信息：
        1. 用户查询：实际用户可能提出的问题
        2. 动作类型：0(直接对话)、1(查询知识库)或2(查询数据库)
        3. 动作参数：对于查询知识库，提供检索关键词；对于查询数据库，提供生成SQL的关键信息
        4. 解释：简短说明为何选择此动作类型
        
        请以JSON格式输出，确保格式正确且内容多样化，覆盖各种复杂度的查询。
        动作类型的分布应大致平衡，但允许适当变化。

        输出示例（请直接输出使用 ```json ```包裹的JSON格式，不要评论，不要其他内容）:

        ```json
        [
            {
                "用户查询": "我的账户余额是多少？",
                "动作类型": 2,
                "动作参数": {'查询内容': '当前用户帐户余额'},
                "解释": "用户想要查询特定账户的余额信息，适合使用数据库查询来获取用户的具体数据。"
            },
            ...
        ]
        ```
        """
    
    async def generate_batch(self, batch_id: int, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """生成一批训练数据"""
        # 从配置获取合法领域
        valid_domains = action_config.get_all_domains()
        selected_domain = domain or random.choice(valid_domains)
        user_prompt = PromptTemplate(text=self.generation_prompt).format({
            "domain": selected_domain,
            "count": self.batch_size
        })
        
        # 调用LLM生成数据
        json_text = ""
        async for x in  self.llm.generate(
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=self.temperature
        ):
            if x.block_type == BlockType.TEXT_FINAL:
                json_text = x.text
            elif x.block_type == BlockType.TEXT_CHUNK:
                print(x.text, end="")
        
        # 解析响应JSON
        try:
            # 更完善的错误处理
            if not json_text:
                print("生成的文本为空")
                return []
            
            # 尝试在完整文本中查找JSON格式
            json_match = re.search(r'\[\s*\{.*\}\s*\]', json_text, re.DOTALL)
            if json_match:
                json_text = json_match.group(0)
            
            # 进一步强化JSON修复
            try:
                data = json.loads(json_text)
            except json.JSONDecodeError:
                # 修复常见JSON错误
                json_text = json_text.replace('""', '"')
                json_text = re.sub(r',\s*\]', ']', json_text)
                json_text = re.sub(r',\s*\}', '}', json_text)
                try:
                    data = json.loads(json_text)
                except:
                    print("JSON修复失败")
                    return []
        except Exception as e:
            print(f"JSON处理错误: {e}")
            return []
            
            # 确保数据是列表格式
            if not isinstance(data, list):
                if 'samples' in data:
                    data = data['samples']
                else:
                    data = [data]
            
            # 添加元数据
            for item in data:
                item['batch_id'] = batch_id
                item['domain'] = selected_domain
                item['timestamp'] = datetime.now().isoformat()
            
            # 字段映射: 中文 -> 英文
            if "用户查询" in item:
                item["user_query"] = item.pop("用户查询")
            if "动作类型" in item:
                item["action_type"] = item.pop("动作类型")
            if "动作参数" in item:
                # 处理动作参数，转换为合适的格式
                params = item.pop("动作参数")
                if item.get("action_type") == 1:  # 查询知识库
                    item["action_params"] = {"query": params}
                elif item.get("action_type") == 2:  # 查询数据库
                    item["action_params"] = {"sql": params}
                else:  # 直接对话
                    item["action_params"] = {}
            if "解释" in item:
                item["explanation"] = item.pop("解释")

            return data
            
    def _format_actions_for_prompt(self) -> str:
        """根据配置生成动作描述"""
        return "\n".join(
            [f"{aid}: {action_config.get_action_name(aid)}" 
             for aid in sorted(action_config.actions.keys())]
        )
    
    async def generate_all_data(self, num_batches: int) -> List[Dict[str, Any]]:
        """生成所有批次的数据"""
        all_data = []
        batch_domains = []
        
        # 为每个批次分配领域，确保领域均衡
        for i in range(num_batches):
            batch_domains.append(DOMAINS[i % len(DOMAINS)])
        
        # 使用tqdm显示进度
        for i in tqdm(range(num_batches), desc="生成训练数据"):
            batch_data = await self.generate_batch(i+1, batch_domains[i])
            if batch_data:
                # 保存单批次数据
                batch_filename = os.path.join(
                    self.output_dir, 
                    f"policy_data_batch_{i+1}_{len(batch_data)}.json"
                )
                with open(batch_filename, 'w', encoding='utf-8') as f:
                    json.dump(batch_data, f, ensure_ascii=False, indent=2)
                
                all_data.extend(batch_data)
                print(f"已保存批次 {i+1} 数据，共 {len(batch_data)} 条")
                
                # 添加延迟以避免API限制
                await asyncio.sleep(1)
        
        # 保存合并数据
        combined_filename = os.path.join(
            self.output_dir,
            f"policy_data_all_{len(all_data)}.json"
        )
        with open(combined_filename, 'w', encoding='utf-8') as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
        
        print(f"已生成并保存全部数据，共 {len(all_data)} 条")
        return all_data
    
    @classmethod
    def analyze_data(cls, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """增强数据分析方法"""
        analysis = {
            "total_samples": len(data),
            "action_distribution": defaultdict(int),
            "domain_distribution": {},
            "query_length_stats": {
                "min": float('inf'),
                "max": 0,
                "avg": 0
            }
        }
        
        # 计算查询长度
        query_lengths = []
        
        for item in data:
            try:
                action_type = int(item.get('action_type', -1))
                if action_type not in action_config.actions:
                    analysis["action_distribution"]["invalid"] += 1
                    continue
                
                # 使用配置获取规范化的动作名称
                action_key = f"{action_type}_{action_config.get_action_name(action_type, 'en').lower()}"
                analysis["action_distribution"][action_key] += 1
            
            except (ValueError, TypeError):
                analysis["action_distribution"]["invalid"] += 1
            
            # 统计领域分布
            domain = item.get('domain', 'unknown')
            if domain not in analysis["domain_distribution"]:
                analysis["domain_distribution"][domain] = 0
            analysis["domain_distribution"][domain] += 1
            
            # 计算查询长度
            query = item.get('user_query', '')
            query_len = len(query)
            query_lengths.append(query_len)
            
            analysis["query_length_stats"]["min"] = min(analysis["query_length_stats"]["min"], query_len)
            analysis["query_length_stats"]["max"] = max(analysis["query_length_stats"]["max"], query_len)
        
        # 计算平均查询长度
        if query_lengths:
            analysis["query_length_stats"]["avg"] = sum(query_lengths) / len(query_lengths)
        
        # 如果没有样本，修正最小长度
        if analysis["query_length_stats"]["min"] == float('inf'):
            analysis["query_length_stats"]["min"] = 0
        
        return analysis
    
    def visualize_analysis(self, analysis: Dict[str, Any], save_path: Optional[str] = None):
        """更健壮的可视化方法"""
        # 过滤非法动作类型
        valid_actions = []
        for k in analysis["action_distribution"].keys():
            if k == "invalid":
                continue
            try:
                action_id = int(k.split('_')[0])
                if action_id in action_config.actions:
                    valid_actions.append(k)
            except:
                pass
        
        # 使用过滤后的动作类型
        action_counts = [analysis["action_distribution"][k] for k in valid_actions]
        action_names = [
            action_config.get_name("action", int(k.split('_')[0]), 'zh' if USE_CHINESE else 'en')
            for k in valid_actions
        ]
        
        # 领域名称映射
        domain_labels = [
            action_config.get_domain_name(d, USE_CHINESE)
            for d in analysis["domain_distribution"].keys()
        ]
        
        plt.figure(figsize=(15, 10))
        
        # 1. 动作类型分布
        plt.subplot(2, 2, 1)
        plt.bar(action_names, action_counts)
        plt.title(get_label('action_distribution'))
        plt.xticks(rotation=45)
        
        # 2. 领域分布
        plt.subplot(2, 2, 2)
        plt.bar(domain_labels, list(analysis["domain_distribution"].values()))
        plt.title(get_label('domain_distribution'))
        plt.xticks(rotation=45)
        
        # 3. 查询长度分布
        plt.subplot(2, 2, 3)
        stats = analysis["query_length_stats"]
        info_text = (
            f"{get_label('min_length')}: {stats['min']} chars\n"
            f"{get_label('max_length')}: {stats['max']} chars\n"
            f"{get_label('avg_length')}: {stats['avg']:.1f} chars"
        )
        plt.text(0.5, 0.5, info_text, 
                ha='center', va='center',
                transform=plt.gca().transAxes, 
                fontsize=12)
        plt.axis('off')
        plt.title(get_label('query_length'))
        
        # 4. 总体统计
        plt.subplot(2, 2, 4)
        time_str = datetime.now().strftime('%Y-%m-%d %H:%M')
        stats_text = (
            f"{get_label('total_samples')}: {analysis['total_samples']}\n"
            f"{get_label('generate_time')}: {time_str}"
        )
        plt.text(0.5, 0.5, stats_text,
                ha='center', va='center',
                transform=plt.gca().transAxes,
                fontsize=12)
        plt.axis('off')
        plt.title(get_label('overall_stats'))
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, bbox_inches='tight')
            print(f"Analysis saved: {save_path}")
        else:
            plt.show()

class DataValidator:
    """训练数据验证器"""
    
    @staticmethod
    def validate_sample(sample: Dict[str, Any]) -> bool:
        """验证单个数据样本格式是否正确"""
        # 必需的字段
        required_fields = ['user_query', 'action_type']
        
        # 检查必需字段是否存在
        for field in required_fields:
            if field not in sample:
                print(f"样本缺少必需字段: {field}")
                return False
        
        # 检查动作类型是否合法
        valid_actions = DOMAIN_MAP['action_types'].keys()
        if sample['action_type'] not in valid_actions:
            print(f"非法动作类型: {sample['action_type']}")
            return False
        
        # 对于查询数据库的动作，检查是否有SQL查询
        if sample['action_type'] == ACTION_QUERY_DATABASE:
            if 'action_params' not in sample or 'sql' not in sample['action_params']:
                print(f"数据库查询样本缺少SQL参数")
                return False
        
        return True
    
    @staticmethod
    def validate_batch(batch_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """验证一批数据的质量"""
        result = {
            "total": len(batch_data),
            "valid_count": 0,
            "invalid_count": 0,
            "action_balance": {
                ACTION_DIRECT_DIALOGUE: 0,
                ACTION_QUERY_KNOWLEDGE: 0, 
                ACTION_QUERY_DATABASE: 0
            }
        }
        
        for sample in batch_data:
            if DataValidator.validate_sample(sample):
                result["valid_count"] += 1
                
                # 统计动作类型分布
                action_type = sample['action_type']
                if action_type in result["action_balance"]:
                    result["action_balance"][action_type] += 1
            else:
                result["invalid_count"] += 1
        
        # 计算动作分布比例
        if result["valid_count"] > 0:
            for action in result["action_balance"]:
                result["action_balance"][action] /= result["valid_count"]
        
        return result

class Training:
    """使用生成的数据进行训练"""
    
    @staticmethod
    async def training(
        data_path: str, 
        num_epochs: int = 5, 
        lr: float = 5e-5, 
        batch_size: int = 16,
        min_lr: float = 1e-6,
        warmup_ratio: float = 0.1,
        grad_clip: float = 1.0,
        early_stop: int = 5,
        fp16: bool = True
    ):
        """进行简单的训练测试，确认数据可用于训练"""
        
        print(f"加载训练数据: {data_path}")
        with open(data_path, 'r', encoding='utf-8') as f:
            training_data = json.load(f)
        
        print(f"共加载 {len(training_data)} 条训练数据")
        
        rocks_db = IndexedRocksDB(EMBEDDING_PATH)
        
        # 初始化嵌入模型
        embeddings = OpenAIEmbeddings(
            model="text-embedding-ada-002",
            imitator="OPENAI",
            dim=1536,
            db=rocks_db  # 使用已初始化的数据库实例
        )
        # 初始化策略网络
        policy_network = PolicyNetwork(confidence_threshold=0.7, model_path=MODEL_PATH, embeddings=embeddings)
        
        # 替换原有优化器配置
        optimizer = torch.optim.AdamW(
            policy_network.parameters(),
            lr=lr,
            weight_decay=0.01
        )
        
        # 添加学习率调度器
        total_steps = num_epochs * (len(training_data) // batch_size + 1)
        scheduler = get_cosine_schedule_with_warmup(
            optimizer,
            num_warmup_steps=int(total_steps * warmup_ratio),
            num_training_steps=total_steps
        )
        
        # 添加设备检测逻辑
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        fp16 = fp16 and torch.cuda.is_available()  # 自动禁用CPU上的混合精度
        print(f"训练设备: {device} | 混合精度: {'启用' if fp16 else '禁用'}")

        # 将模型转移到对应设备
        policy_network = policy_network.to(device)

        # 初始化记录结构
        train_results = {
            'train_losses': [],
            'val_accuracies': [],
            'learning_rates': [],
            'best_val_acc': 0.0,
            'batch_evolution': [],
            'final_train_loss': 0.0  # 新增初始化
        }

        # 修改训练循环
        for epoch in range(num_epochs):
            policy_network.train()
            total_loss = 0.0
            
            # 使用DataLoader改进数据加载
            dataloader = DataLoader(
                training_data,
                batch_size=batch_size,
                shuffle=True,
                num_workers=4,
                collate_fn=collate_fn
            )
            
            for batch_idx, batch in enumerate(dataloader):
                queries, action_types = batch
                action_types = action_types.to(device)  # 转移标签到设备

                # 获取原始嵌入数据（保持通用接口）
                embedding_texts = policy_network.embeddings.sync_embed_texts(queries)
                
                # 正确提取向量并转换为Tensor
                vectors = []
                for emb in embedding_texts:
                    # 类型校验
                    if not isinstance(emb, EmbeddingText):
                        raise TypeError(f"期望EmbeddingText类型，实际得到: {type(emb)}")
                    
                    # 向量转换
                    vector = emb.vector
                    if isinstance(vector, list):
                        vector = torch.tensor(vector, dtype=torch.float32)
                    elif isinstance(vector, np.ndarray):
                        vector = torch.from_numpy(vector).float()
                    
                    # 添加维度校验
                    if vector.dim() == 1:
                        vector = vector.unsqueeze(0)  # 添加批次维度 (1536) -> (1, 1536)
                    elif vector.dim() > 2:
                        vector = vector.squeeze()
                    
                    vectors.append(vector.to(device))

                # 统一堆叠处理
                try:
                    stacked_vectors = torch.cat(vectors, dim=0)  # 使用cat代替stack处理不同长度
                except RuntimeError as e:
                    print(f"向量堆叠失败，各向量形状: {[v.shape for v in vectors]}")
                    raise

                # 后续统一使用vectors
                # print(f"输入向量形状: {stacked_vectors.shape}")  # 应为 (batch_size, 1536)

                with torch.cuda.amp.autocast(enabled=fp16):
                    outputs = policy_network(stacked_vectors)
                    logits = outputs["action_logits"]
                    probs = F.softmax(logits, dim=-1)  # 显式计算概率
                    
                    # 强化维度检查
                    if logits.dim() not in [2, 3]:
                        raise RuntimeError(f"非法logits维度: {logits.shape}")
                        
                    if logits.dim() == 3:
                        # 自动选择压缩维度
                        if logits.shape[1] == 1:  # (batch, 1, actions)
                            logits = logits.squeeze(1)
                        else:  # (batch, actions, 1)
                            logits = logits.squeeze(-1)
                    
                    # 最终维度断言
                    assert logits.dim() == 2, f"修正后维度异常: {logits.shape}"
                    
                    loss = F.cross_entropy(logits, action_types)
                
                # 反向传播
                loss.backward()
                
                # 梯度裁剪
                torch.nn.utils.clip_grad_norm_(
                    policy_network.parameters(),
                    grad_clip
                )
                
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad()
                
                total_loss += loss.item()
                
                # 进度日志
                if batch_idx % 10 == 0:
                    current_lr = optimizer.param_groups[0]['lr']
                    print(f"Epoch {epoch+1} | Batch {batch_idx} | Loss: {loss.item():.4f} | LR: {current_lr:.2e}")
            
            avg_epoch_loss = total_loss / (len(training_data) // batch_size + 1)
            print(f"第 {epoch+1} 轮平均损失: {avg_epoch_loss:.4f}")
            
            # 添加验证逻辑
            val_acc = await policy_network.validate(training_data)
            train_results['val_accuracies'].append(val_acc)
            if val_acc > train_results['best_val_acc']:
                train_results['best_val_acc'] = val_acc
            
            # 记录训练损失
            train_results['train_losses'].append(avg_epoch_loss)
            train_results['learning_rates'].append(current_lr)
            
            # 添加批次演进
            train_results['batch_evolution'].append(f"Epoch {epoch+1}")
            
            # 在每个epoch结束时更新
            train_results['final_train_loss'] = avg_epoch_loss
            
            # 最终返回前再次确认
            if not train_results['final_train_loss'] and train_results['train_losses']:
                train_results['final_train_loss'] = train_results['train_losses'][-1]
        
        await policy_network.save()  # 确保异步保存
        
        return train_results  # 返回完整结果字典
    
    @staticmethod
    async def evaluate_model(policy_network, test_data, num_samples=20):
        """评估训练好的模型"""
        from anyio import create_task_group, CapacityLimiter
        
        # 初始化配置
        eval_samples = random.sample(test_data, min(num_samples, len(test_data)))
        MAX_CONCURRENT = 8  # 最大并发数
        TIMEOUT = 15.0      # 单次预测超时
        results = []
        correct = 0
        
        async def process_sample(sample):
            nonlocal correct
            query = sample["user_query"][:200]  # 限制查询长度
            true_action = sample["action_type"]
            
            try:
                # 修正预测调用
                prediction = await asyncio.wait_for(
                    policy_network.predict(query),
                    timeout=TIMEOUT
                )
                # 确保action_type是标量值
                if isinstance(prediction.action_type, torch.Tensor):
                    pred_action = prediction.action_type.item()
                else:
                    pred_action = prediction.action_type
            except Exception as e:
                logger.error(f"预测失败: {str(e)}")
                return None

            # 记录结果
            is_correct = (pred_action == true_action)
            result = {
                "query": query,
                "true_action": true_action,
                "pred_action": pred_action,
                "confidence": round(prediction.confidence, 4),
                "correct": is_correct
            }

            if is_correct:
                correct += 1
            
            return result

        try:
            # 使用任务组管理并发
            async with create_task_group() as tg:
                limiter = CapacityLimiter(MAX_CONCURRENT)
                task_queue = []

                # 创建并调度任务
                for sample in eval_samples:
                    async def wrapped_task(sample):
                        async with limiter:
                            return await process_sample(sample)
                    task = tg.start_soon(wrapped_task, sample)
                    task_queue.append(task)

            # 收集结果
            results = [t.result() for t in task_queue if t.completed]
        except Exception as e:
            logging.critical(f"评估过程异常: {str(e)}")

        # 过滤有效结果
        valid_results = [r for r in results if r is not None]
        accuracy = len(valid_results) / len(eval_samples) if eval_samples else 0

        # 异步保存结果
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: json.dump(
                {
                    "accuracy": accuracy,
                    "action_names": ACTION_NAMES,
                    "results": valid_results
                },
                open(f"{DATA_PATH}/evaluation_results.json", "w"),
                ensure_ascii=False,
                indent=2
            )
        )

        return accuracy, valid_results

class DataAnalyzer:
    """数据分析工具类"""
    
    def analyze_data(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析训练数据"""
        # 使用与TrainingDataGenerator相同的分析逻辑...
        return TrainingDataGenerator.analyze_data(data)
    
    def visualize_analysis(self, analysis: Dict[str, Any], save_path: Optional[str] = None):
        """可视化分析结果"""
        # 动作名称映射
        action_names = [
            action_config.get_action_name(int(k.split('_')[0]), USE_CHINESE)
            for k in analysis["action_distribution"].keys()
        ]
        
        # 领域名称映射
        domain_labels = [
            action_config.get_domain_name(d, USE_CHINESE)
            for d in analysis["domain_distribution"].keys()
        ]
        
        plt.figure(figsize=(15, 10))
        
        # 1. 动作类型分布
        plt.subplot(2, 2, 1)
        action_counts = list(analysis["action_distribution"].values())
        plt.bar(action_names, action_counts)
        plt.title(get_label('action_distribution'))
        plt.xticks(rotation=45)
        
        # 2. 领域分布
        plt.subplot(2, 2, 2)
        domain_counts = list(analysis["domain_distribution"].values())
        plt.bar(domain_labels, domain_counts)
        plt.title(get_label('domain_distribution'))
        plt.xticks(rotation=45)
        
        # 3. 查询长度分布
        plt.subplot(2, 2, 3)
        stats = analysis["query_length_stats"]
        info_text = (
            f"{get_label('min_length')}: {stats['min']} chars\n"
            f"{get_label('max_length')}: {stats['max']} chars\n"
            f"{get_label('avg_length')}: {stats['avg']:.1f} chars"
        )
        plt.text(0.5, 0.5, info_text, 
                ha='center', va='center',
                transform=plt.gca().transAxes, 
                fontsize=12)
        plt.axis('off')
        plt.title(get_label('query_length'))
        
        # 4. 总体统计
        plt.subplot(2, 2, 4)
        time_str = datetime.now().strftime('%Y-%m-%d %H:%M')
        stats_text = (
            f"{get_label('total_samples')}: {analysis['total_samples']}\n"
            f"{get_label('generate_time')}: {time_str}"
        )
        plt.text(0.5, 0.5, stats_text,
                ha='center', va='center',
                transform=plt.gca().transAxes,
                fontsize=12)
        plt.axis('off')
        plt.title(get_label('overall_stats'))
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, bbox_inches='tight')
            print(f"Analysis saved: {save_path}")
        else:
            plt.show()

def collate_fn(batch: List[Dict]):
    """自定义批次处理"""
    return (
        [x["user_query"] for x in batch],
        torch.tensor([x["action_type"] for x in batch])
    )

def generate_training_report(results: dict):
    """生成训练报告"""
    report = f"""
## 训练报告
- 最佳验证准确率: {results['best_val_acc']:.2%}
- 最终训练损失: {results['final_train_loss']:.4f}
- 总训练时间: {results['total_time']:.1f}s
- 使用批次演进: {results['batch_evolution']}
    """
    print(report)

def generate_enhanced_report(results: dict, path: str):
    """增强健壮性的报告生成"""
    # 添加默认值处理
    final_loss = results.get('final_train_loss', results.get('train_losses', [0.0])[-1] if results.get('train_losses') else 0.0)
    best_val_acc = results.get('best_val_acc', 0.0)
    
    content = f"""
## 增强训练报告
### 核心指标
- 最佳验证准确率: {best_val_acc:.2%}
- 最终训练损失: {final_loss:.4f}
- 训练轮次: {len(results.get('train_losses', []))}
- 使用批次大小: {set(results.get('batch_evolution', []))}

### 学习曲线
![损失曲线](./enhanced_training_loss.png)

### 详细数据
| 轮次 | 训练损失 | 验证准确率 | 学习率    |
|------|----------|------------|-----------|
"""
    for i, (loss, acc, lr) in enumerate(zip(
        results['train_losses'],
        results['val_accuracies'],
        results['learning_rates']
    )):
        content += f"| {i+1} | {loss:.4f} | {acc:.2%} | {lr:.2e} |\n"

    with open(path, 'w') as f:
        f.write(content)

async def main():
    """简化后的训练入口"""
    parser = argparse.ArgumentParser(description='策略网络训练数据生成工具')
    parser.add_argument('--batches', type=int, default=1, help='要生成的批次数量')
    parser.add_argument('--batch-size', type=int, default=5, help='每批数据量')
    parser.add_argument('--model', type=str, default='gpt-4o-mini', help='使用的LLM模型')
    parser.add_argument('--imitator', type=str, default=None, help='模型提供商')
    parser.add_argument('--output', type=str, default=DATA_PATH, help='输出目录')
    parser.add_argument('--analyze', action='store_true', help='是否分析生成的数据')
    parser.add_argument('--validate', action='store_true', help='是否验证生成的数据')
    parser.add_argument('--train', action='store_true', help='是否进行训练测试')
    parser.add_argument('--data-file', type=str, default=None, 
                        help='直接使用现有的数据文件路径，跳过生成步骤')
    parser.add_argument('--epochs', type=int, default=10, help='训练轮次')
    parser.add_argument('--lr', type=float, default=3e-5, help='初始学习率（默认3e-5）')
    parser.add_argument('--warmup', type=float, default=0.1, help='学习率热启动比例（默认0.1）')
    parser.add_argument('--min-lr', type=float, default=1e-6, help='最小学习率（默认1e-6）')
    parser.add_argument('--grad-clip', type=float, default=1.0, help='梯度裁剪阈值（默认1.0）')
    parser.add_argument('--early-stop', type=int, default=5, help='早停耐心值（默认5轮）')
    
    args = parser.parse_args()
    
    all_data = []
    
    # 判断是生成新数据还是使用现有数据
    if args.data_file:
        # 使用现有数据文件
        print(f"加载现有数据文件: {args.data_file}")
        try:
            with open(args.data_file, 'r', encoding='utf-8') as f:
                all_data = json.load(f)
            print(f"成功加载 {len(all_data)} 条数据")
        except Exception as e:
            print(f"加载数据文件失败: {e}")
            return
    else:
        # 创建数据生成器并生成新数据
        generator = TrainingDataGenerator(
        output_dir=args.output,
        model=args.model,
        imitator=args.imitator,
        batch_size=args.batch_size
    )    
        print(f"开始生成 {args.batches} 批训练数据，每批 {args.batch_size} 条...")
        all_data = await generator.generate_all_data(args.batches)
    
    # 确保数据不为空再继续
    if not all_data:
        print("没有有效数据，终止处理")
        return
    
    # 验证数据
    if args.validate:
        print("验证生成的数据...")
        validator = DataValidator()
        validation_result = validator.validate_batch(all_data)
        print(f"验证结果: 有效样本 {validation_result['valid_count']}/{validation_result['total']}")
        print(f"动作分布: {validation_result['action_balance']}")
    
    # 分析数据
    if args.analyze:
        print("分析生成的数据...")
        analysis = generator.analyze_data(all_data) if 'generator' in locals() else DataAnalyzer().analyze_data(all_data)
        
        # 修复分析阶段错误，为空数据添加保护
        print(f"分析结果: 共 {analysis['total_samples']} 条样本")
        print(f"动作分布: {analysis['action_distribution']}")
        
        # 创建DataAnalyzer类处理分析和可视化
        analyzer = DataAnalyzer()
        # 可视化分析结果
        analyzer.visualize_analysis(
            analysis, 
            save_path=os.path.join(args.output, "data_analysis.png")
        )
    
    # 进行训练测试（替换原有训练流程）
    if args.train:
        print("启动增强训练流程...")
        # 自动创建合并数据文件
        combined_file = args.data_file or os.path.join(args.output, f"policy_data_all_{len(all_data)}.json")
        if not os.path.exists(combined_file):
            with open(combined_file, 'w', encoding='utf-8') as f:
                json.dump(all_data, f, ensure_ascii=False, indent=2)

        # 执行增强训练并获取完整结果
        train_results = await Training.training(
            data_path=combined_file,
            num_epochs=args.epochs,
            lr=args.lr,
            batch_size=args.batch_size,
            warmup_ratio=args.warmup,
            grad_clip=args.grad_clip,
            early_stop=args.early_stop
        )

        # 生成增强版报告
        report_path = os.path.join(DATA_PATH, "enhanced_training_report.md")
        generate_enhanced_report(train_results, report_path)
        print(f"增强训练报告已保存: {report_path}")

if __name__ == "__main__":
    asyncio.run(main())

    