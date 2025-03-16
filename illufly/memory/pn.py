from typing import List, Dict, Tuple, Any, Optional
from dataclasses import dataclass
from datetime import datetime

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import json
import random
import logging
import asyncio
import os
import re

# 导入您封装的向量模型
from ..community.openai import OpenAIEmbeddings, ChatOpenAI

# 配置日志
logger = logging.getLogger(__name__)

@dataclass
class ActionSpace:
    """动作空间定义"""
    DIRECT_DIALOGUE: int = 0      # 直接对话
    QUERY_KNOWLEDGE: int = 1      # 查询知识库  
    QUERY_DATABASE: int = 2       # 查询数据库

@dataclass
class PolicyPrediction:
    """策略网络预测结果"""
    action_type: int              # 动作类型
    confidence: float             # 置信度
    action_params: Dict           # 动作参数 (例如查询语句)
    probabilities: List[float]    # 所有动作的概率分布

class MemoryBuffer:
    """记忆缓冲区，用于在线学习"""
    def __init__(self, capacity: int = 1000):
        self.capacity = capacity
        self.buffer = []
        self.priorities = []
        
    def add(self, sample: Dict, priority: float = 1.0):
        """添加样本到缓冲区"""
        if len(self.buffer) >= self.capacity:
            # 移除最低优先级样本
            min_idx = np.argmin(self.priorities)
            self.buffer.pop(min_idx)
            self.priorities.pop(min_idx)
            
        self.buffer.append(sample)
        self.priorities.append(priority)
    
    def sample(self, batch_size: int) -> List[Dict]:
        """采样一批数据"""
        if not self.buffer:
            return []
        indices = np.random.choice(
            len(self.buffer),
            min(batch_size, len(self.buffer)),
            p=np.array(self.priorities) / sum(self.priorities),
            replace=False
        )
        return [self.buffer[i] for i in indices]
    
    def clear(self):
        """清空缓冲区"""
        self.buffer = []
        self.priorities = []
        
    def __len__(self):
        return len(self.buffer)

class QueryGenerator(nn.Module):
    """查询生成器"""
    def __init__(self, input_dim: int, hidden_dim: int):
        super().__init__()
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim)
        
    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = self.fc2(x)
        return x

class PolicyNetwork(nn.Module):
    """策略网络主模型"""
    def __init__(
        self, 
        embeddings: OpenAIEmbeddings = None,
        actions: List[str] = None,
        confidence_threshold: float = 0.7,
        model_path: str = None,  # 新增参数：模型路径
        imitator: str = None     # 新增参数：用于加载模型时指定
    ):
        super().__init__()
        # 初始化向量模型
        self.embeddings = embeddings or OpenAIEmbeddings(
            model="text-embedding-ada-002",
            imitator="OPENAI",
            dim=1536
        )
        self.hidden_dim = self.embeddings.dim
        
        # 动作空间定义与管理
        self.action_names = actions or ["直接对话", "查询知识库", "查询数据库"]
        self.action_space_size = len(self.action_names)
        
        # 统一使用英文键名
        self.action_key_map = {
            "直接对话": "direct",
            "查询知识库": "knowledge",
            "查询数据库": "database"
        }
        
        # 置信度阈值
        self.confidence_threshold = confidence_threshold
        
        # 延迟初始化关键组件
        self.decision_head = None
        self.query_generators = None
        
        # 如果提供模型路径，立即加载
        self.model_path = model_path or "./models"
        if model_path:
            logger.info(f"模型加载路径: {self.model_path}")
            self._load_pretrained(self.model_path)
        else:
            # 无模型时初始化基础结构
            self._rebuild_network()
        
        # 在线学习组件
        self.memory = MemoryBuffer(capacity=1000)
        
        # 将优化器初始化移到最后
        self._init_optimizer()  # 新增优化器初始化方法
        
        # 添加动作注册表（新增）
        self._action_registry = {
            "direct": "直接对话",
            "knowledge": "查询知识库", 
            "database": "查询数据库",
            "external_api": "调用外部API"  # 新增标准动作
        }
        
    def _init_optimizer(self):
        """独立优化器初始化方法"""
        params = list(self.decision_head.parameters())
        for generator in self.query_generators.values():
            params += list(generator.parameters())
        
        # 初始化优化器
        self.optimizer = torch.optim.AdamW(params, lr=1e-5)
        logger.debug("优化器初始化完成，参数数量: %d", len(params))
        
    def _load_pretrained(self, model_path: str):
        """加载预训练模型（增强错误处理）"""
        try:
            if os.path.isfile(model_path):
                return self._load_from_file(model_path)
            elif os.path.isdir(model_path):
                latest_model = self._find_latest_model(model_path)
                if latest_model:
                    return self._load_from_file(latest_model)
                return False
            else:
                logger.error(f"无效模型路径: {model_path}")
                return False
        except Exception as e:
            logger.error(f"模型加载失败: {str(e)}", exc_info=True)
            # 尝试恢复初始状态
            self._init_optimizer()
            return False
        
    def _find_latest_model(self, model_dir: str) -> Optional[str]:
        """改进的最新模型查找方法"""
        model_files = []
        for f in os.listdir(model_dir):
            if f.startswith('policy_network_') and f.endswith('.pt'):
                try:
                    # 从文件名解析时间戳
                    timestamp_str = re.search(r'policy_network_(\d{8}_\d{6})', f).group(1)
                    timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                    model_files.append((f, timestamp))
                except:
                    continue
        
        if not model_files:
            return None
        
        # 按时间戳降序排序
        sorted_models = sorted(model_files, key=lambda x: x[1], reverse=True)
        return os.path.join(model_dir, sorted_models[0][0])
        
    def _load_from_file(self, path: str) -> bool:
        try:
            save_dict = torch.load(path)
            # 添加版本检查
            if "version" not in save_dict or save_dict["version"] != "2.4":
                logger.warning("检测到旧版模型格式，建议进行迁移")
            
            # 优先使用模型自带的动作列表
            if 'action_names' in save_dict:
                self.action_names = save_dict['action_names']
                self.action_space_size = len(self.action_names)
                logger.info(f"从模型加载动作空间: {self.action_names}")
            
            # 同步键名映射
            self.action_key_map = save_dict.get('action_key_map', self.action_key_map)
            
            # 动态重建网络结构
            self._rebuild_network()
            
            # 键名转换
            new_state_dict = {}
            for k, v in save_dict['model_state'].items():
                new_k = re.sub(r'query_generators.(\W+)', 
                             lambda m: f"query_generators.{self.action_key_map.get(m.group(1), m.group(1))}", k)
                new_state_dict[new_k] = v
            
            # 严格模式加载
            self.load_state_dict(new_state_dict, strict=True)
            return True
        except Exception as e:
            logger.error(f"模型加载失败: {str(e)}")
            return False

    def _rebuild_network(self):
        """根据当前动作空间重建网络组件"""
        # 重建决策头
        self.decision_head = nn.Linear(self.hidden_dim, self.action_space_size)
        
        # 重建查询生成器
        self.query_generators = nn.ModuleDict()
        for action in self.action_names:
            action_key = self.action_key_map.get(action, action.lower().replace(" ", "_"))
            self.query_generators[action_key] = QueryGenerator(self.hidden_dim, self.hidden_dim)
        
        # 重新初始化优化器
        self._init_optimizer()

    def _sync_action_space(self, new_actions: List[str]):
        """同步动作空间到最新状态"""
        # 添加缺失动作（带存在性检查）
        added_actions = []
        for action in new_actions:
            if action not in self.action_names:
                success = self.add_action(action, init_strategy='average')
                if success:
                    added_actions.append(action)
        
        logger.info(f"同步动作空间完成，新增动作: {added_actions}")

    def _adjust_network_structure(self, target_actions: List[str]):
        """动态调整网络结构"""
        # 调整决策头
        if len(target_actions) != self.action_space_size:
            logger.info(f"调整决策头维度 {self.action_space_size} → {len(target_actions)}")
            old_head = self.decision_head
            self.decision_head = nn.Linear(self.hidden_dim, len(target_actions))
            
            # 复制已有权重
            with torch.no_grad():
                if old_head.weight.shape[0] <= self.decision_head.weight.shape[0]:
                    self.decision_head.weight[:old_head.weight.shape[0]] = old_head.weight
                    self.decision_head.bias[:old_head.bias.shape[0]] = old_head.bias

        # 同步查询生成器
        for action in target_actions:
            action_key = self.action_key_map.get(action, action.lower().replace(" ", "_"))
            if action_key not in self.query_generators:
                self.query_generators[action_key] = QueryGenerator(self.hidden_dim, self.hidden_dim)

    async def encode_text(self, text: str) -> torch.Tensor:
        """使用OpenAI API编码文本"""
        # 使用封装的embed_texts方法获取向量
        embedding_texts = await self.embeddings.embed_texts([text])
        vector = embedding_texts[0].vector
        
        # 转换为张量并添加批次维度
        return torch.tensor(vector).unsqueeze(0)
    
    def forward(self, encoded_text: torch.Tensor) -> Dict[str, torch.Tensor]:
        """前向传播"""
        # 动作决策
        action_logits = self.decision_head(encoded_text)
        action_probs = F.softmax(action_logits, dim=1)
        
        # 针对不同动作生成查询
        query_knowledge = self.query_generators["knowledge"](encoded_text)
        query_database = self.query_generators["database"](encoded_text)
        
        return {
            "action_logits": action_logits,
            "action_probs": action_probs,
            "query_knowledge": query_knowledge,
            "query_database": query_database
        }
    
    async def predict(self, query: str) -> PolicyPrediction:
        """预测用户查询的处理策略"""
        self.eval()
        
        # 编码查询
        encoded_query = await self.encode_text(query)
        
        # 获取模型输出
        with torch.no_grad():
            outputs = self.forward(encoded_query)
        
        # 获取动作概率
        action_probs = outputs["action_probs"].cpu().numpy()[0]
        
        # 选择最高概率动作
        action_type = int(np.argmax(action_probs))
        confidence = float(action_probs[action_type])
        
        # 准备动作参数
        action_params = {}
        if action_type == ActionSpace.QUERY_KNOWLEDGE:
            # 生成知识库查询语句
            action_params["query"] = query
        elif action_type == ActionSpace.QUERY_DATABASE:
            # 生成数据库查询语句
            action_params["sql"] = f"SELECT * FROM relevant_table WHERE content LIKE '%{query}%'"
            
        return PolicyPrediction(
            action_type=action_type,
            confidence=confidence,
            action_params=action_params,
            probabilities=action_probs.tolist()
        )
    
    async def online_update(self, query: str, action_type: int, action_params: Dict, priority: float = 1.0):
        """在线更新模型参数"""
        # 存储样本到记忆缓冲区
        sample = {
            "query": query,
            "action_type": action_type,
            "action_params": action_params,
            "timestamp": datetime.now().isoformat()
        }
        self.memory.add(sample, priority)
        
        # 当积累足够样本时执行更新
        if len(self.memory) >= 16:
            await self._update_parameters()
    
    async def _update_parameters(self, batch_size: int = 16):
        """执行参数更新"""
        batch = self.memory.sample(batch_size)
        if not batch:
            return
            
        self.train()
        self.optimizer.zero_grad()
        
        # 准备批次数据
        queries = [item["query"] for item in batch]
        action_types = torch.tensor([item["action_type"] for item in batch])
        
        # 批量获取文本嵌入
        embedding_texts = await self.embeddings.embed_texts(queries)
        vectors = [emb.vector for emb in embedding_texts]
        
        # 转换为张量
        encoded_queries = torch.tensor(vectors)
        
        # 前向传播
        outputs = self.forward(encoded_queries)
        
        # 计算分类损失
        loss = F.cross_entropy(outputs["action_logits"], action_types)
        
        # 反向传播和优化
        loss.backward()
        self.optimizer.step()
        
        logger.info(f"在线更新完成，损失: {loss.item():.4f}")
        
    def add_action(self, action_name: str, init_strategy: str = 'default'):
        """增强型动作添加方法"""
        if action_name in self.action_names:
            logger.warning(f"动作 '{action_name}' 已存在，跳过添加")
            return False  # 明确返回False避免重复添加
        
        # 记录原始结构
        original_size = self.action_space_size
        
        # 添加新动作
        self.action_names.append(action_name)
        self.action_space_size += 1
        
        # 扩展决策头
        new_head = nn.Linear(self.hidden_dim, self.action_space_size)
        
        # 权重初始化策略
        with torch.no_grad():
            if init_strategy == 'zero':
                new_head.weight[-1:] = 0
                new_head.bias[-1:] = 0
            elif init_strategy == 'random':
                nn.init.xavier_normal_(new_head.weight[-1:])
                nn.init.zeros_(new_head.bias[-1:])
            else:  # 默认使用平均初始化
                avg_weight = torch.mean(self.decision_head.weight, dim=0)
                new_head.weight[:-1] = self.decision_head.weight
                new_head.weight[-1:] = avg_weight.unsqueeze(0)
                new_head.bias[:-1] = self.decision_head.bias
                new_head.bias[-1:] = torch.mean(self.decision_head.bias)
        
        self.decision_head = new_head
        
        # 添加查询生成器
        action_key = self.action_key_map.get(action_name, action_name.lower().replace(" ", "_"))
        self.query_generators[action_key] = QueryGenerator(self.hidden_dim, self.hidden_dim)
        
        # 更新优化器
        self._update_optimizer()
        
        logger.info(f"成功添加动作: {action_name} (初始化策略: {init_strategy})")
        return True

    def _update_optimizer(self):
        """更新优化器参数集合"""
        params = list(self.decision_head.parameters())
        for generator in self.query_generators.values():
            params += list(generator.parameters())
        
        # 创建新优化器，保留原有动量等状态
        old_opt = self.optimizer
        self.optimizer = torch.optim.AdamW(params, lr=old_opt.param_groups[0]['lr'])
        
        # 迁移优化器状态（可选）
        # 实际应用中需要更复杂的状态迁移逻辑

    async def save(self, path: str = None):
        """增强版模型保存，自动生成时间戳文件名"""
        # 将文件操作放入线程池执行
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,  # 使用默认线程池
            self._actual_save,  # 实际保存逻辑
            path
        )

    def _actual_save(self, path: str):
        """实际同步保存逻辑"""
        if not path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(self.model_path, f"policy_network_{timestamp}.pt")
        else:
            path = os.path.join(self.model_path, os.path.basename(path))
        
        save_dict = {
            "model_state": self.state_dict(),
            "action_names": self.action_names,
            "timestamp": datetime.now().timestamp(),
            "version": "2.4"
        }
        os.makedirs(os.path.dirname(path), exist_ok=True)
        torch.save(save_dict, path)
        logger.info(f"模型已保存至: {path}")
    
    @classmethod
    def load(cls, path: str, embeddings: OpenAIEmbeddings):
        """加载时处理键名兼容"""
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        save_dict = torch.load(path, map_location=device)
        
        # 键名转换逻辑
        state_dict = save_dict["model_state"]
        new_state_dict = {}
        for k, v in state_dict.items():
            new_k = k.replace("查询知识库", "knowledge").replace("查询数据库", "database")
            new_state_dict[new_k] = v
        
        # 初始化网络
        net = cls(
            embeddings=embeddings,
            confidence_threshold=save_dict.get("confidence_threshold", 0.7)
        )
        net.load_state_dict(new_state_dict)
        
        return net

    def validate_actions(self, actions: List[str]) -> bool:
        """验证动作列表兼容性（新增）"""
        valid = True
        for action in actions:
            if action not in self._action_registry.values():
                logger.warning(f"未注册的动作: {action}")
                valid = False
        return valid

    async def train_network(
        self,
        train_data: List[Dict],
        val_data: Optional[List[Dict]] = None,
        epochs: int = 10,
        batch_size: int = 32,
        lr: float = 5e-5,
        save_dir: str = None
    ):
        """内置训练方法"""
        self.optimizer = torch.optim.AdamW(self.parameters(), lr=lr)
        
        best_acc = 0
        for epoch in range(epochs):
            self.train()
            total_loss = 0.0  # 改为浮点数
            
            random.shuffle(train_data)
            
            # 分批处理（异步）
            for i in range(0, len(train_data), batch_size):
                batch = train_data[i:i+batch_size]
                loss = await self._train_batch(batch)  # 添加await
                total_loss += loss
                
            # 验证阶段
            val_acc = 0
            if val_data:
                val_acc = await self.validate(val_data)
                if val_acc > best_acc:
                    await self.save(os.path.join(save_dir, "best_model.pt"))
                    best_acc = val_acc
            
            # 保存检查点
            if save_dir:
                await self.save(os.path.join(save_dir, f"epoch_{epoch+1}.pt"))
        
        return {"final_val_acc": best_acc}

    async def _train_batch(self, batch: List[Dict]) -> float:
        """处理单个训练批次"""
        self.optimizer.zero_grad()
        
        # 准备数据
        queries = [item["user_query"] for item in batch]
        action_types = torch.tensor([item["action_type"] for item in batch])
        
        # 获取嵌入
        embedding_texts = await self.embeddings.embed_texts(queries)
        vectors = [emb.vector for emb in embedding_texts]
        encoded_queries = torch.tensor(vectors)
        
        # 前向传播
        outputs = self.forward(encoded_queries)
        loss = F.cross_entropy(outputs["action_logits"], action_types)
        
        # 反向传播
        loss.backward()
        self.optimizer.step()
        
        return loss.item()

    async def validate(self, val_data: List[Dict]) -> float:
        """验证集评估"""
        correct = 0
        for item in val_data:
            pred = await self.predict(item["user_query"])
            if pred.action_type == item["action_type"]:
                correct += 1
        return correct / len(val_data)

class LLMInterface:
    """大模型接口，用于低置信度情况下的预测"""
    def __init__(self, **kwargs):
        self.llm = ChatOpenAI(**kwargs)
        # 实际应用中这里应该实现与特定大模型API的连接
        # 例如OpenAI API, Claude API等
        
    async def predict(self, query: str) -> Tuple[int, Dict]:
        """调用大模型进行预测"""
        # 这里是模拟实现，实际应用需替换为真实API调用
        # 格式化提示词
        prompt = f"""
        分析以下用户问题，并决定应采取的行动：
        1. 直接对话回答
        2. 查询知识库
        3. 查询数据库
        
        用户问题: {query}
        
        请输出JSON格式结果，包含决策类型和详细参数:
        """
        
        # 模拟大模型响应
        import random
        action_type = random.choice([0, 1, 2])
        
        if action_type == 0:  # 直接对话
            response = {"action": "direct_dialogue", "params": {}}
        elif action_type == 1:  # 查询知识库
            response = {
                "action": "query_knowledge", 
                "params": {"query": query, "filter": "relevant"}
            }
        else:  # 查询数据库
            response = {
                "action": "query_database", 
                "params": {"sql": f"SELECT * FROM data WHERE content LIKE '%{query}%'"}
            }
            
        # 转换为内部动作类型
        action_mapping = {
            "direct_dialogue": ActionSpace.DIRECT_DIALOGUE,
            "query_knowledge": ActionSpace.QUERY_KNOWLEDGE,
            "query_database": ActionSpace.QUERY_DATABASE
        }
        
        return action_mapping[response["action"]], response["params"]

class PolicyAgent:
    """策略代理，整合策略网络和大模型"""
    def __init__(
        self, 
        policy_network: Optional[PolicyNetwork] = None,
        llm_interface: Optional[LLMInterface] = None,
        model_path: str = None,
        confidence_threshold: float = 0.7,
        auto_load: bool = True    # 新增参数：是否自动加载最新模型
    ):        
        # 如果未提供policy_network且启用了自动加载
        if policy_network is None and auto_load:
            # 创建策略网络并加载模型
            policy_network = PolicyNetwork(
                model_path=model_path,
                confidence_threshold=confidence_threshold
            )
        
        # 如果仍未创建策略网络，则创建一个新的
        if policy_network is None:
            policy_network = PolicyNetwork(confidence_threshold=confidence_threshold)
            
        self.policy_network = policy_network
        
        # 如果未提供llm_interface，创建一个
        self.llm = llm_interface or LLMInterface()
        
        # 使用策略网络中的置信度阈值（如果已经加载了模型）
        self.confidence_threshold = policy_network.confidence_threshold
        
    async def process_query(self, query: str) -> Dict:
        """处理用户查询"""
        # 策略网络预测
        prediction = await self.policy_network.predict(query)
        
        # 判断是否使用策略网络结果
        if prediction.confidence >= self.confidence_threshold:
            logger.info(
                f"使用策略网络预测: {self.policy_network.action_names[prediction.action_type]}, "
                f"置信度: {prediction.confidence:.4f}"
            )
            
            action_type = prediction.action_type
            action_params = prediction.action_params
            source = "policy_network"
        else:
            # 低置信度时调用大模型
            logger.info(f"策略网络置信度不足 ({prediction.confidence:.4f}), 调用大模型")
            action_type, action_params = await self.llm.predict(query)
            
            # 在线更新策略网络
            await self.policy_network.online_update(
                query=query, 
                action_type=action_type, 
                action_params=action_params,
                priority=1.0  # 可以基于某些指标调整优先级
            )
            source = "llm"
            
        # 准备结果
        return {
            "action_type": action_type,
            "action_name": self.policy_network.action_names[action_type],
            "action_params": action_params,
            "source": source,
            "all_probabilities": prediction.probabilities
        }
    
    def execute_action(self, action_result: Dict) -> str:
        """执行动作（模拟实现）"""
        action_type = action_result["action_type"]
        action_params = action_result["action_params"]
        
        if action_type == ActionSpace.DIRECT_DIALOGUE:
            return "使用直接对话回应用户"
        elif action_type == ActionSpace.QUERY_KNOWLEDGE:
            return f"查询知识库: {action_params.get('query', '')}"
        elif action_type == ActionSpace.QUERY_DATABASE:
            return f"执行SQL查询: {action_params.get('sql', '')}"
        else:
            return f"执行未知动作类型: {action_type}"
    
    async def monthly_update(self, dataset_path: Optional[str] = None):
        """执行月度更新"""
        # 使用缓冲区中的数据或加载外部数据集
        if dataset_path:
            # 加载外部数据集
            # dataset = load_dataset(dataset_path)
            pass
        
        # 使用记忆缓冲区中的数据进行完整更新
        logger.info(f"开始月度更新，使用 {len(self.policy_network.memory)} 个样本")
        
        # 在实际应用中，这里应该实现更完整的训练循环
        # 包括数据划分、多轮训练、验证等
        
        # 保存更新后的模型
        timestamp = datetime.now().strftime("%Y%m%d")
        await self.policy_network.save(f"{self.policy_network.model_path}/policy_network_{timestamp}.pt")
        
        # 清空或保留部分记忆缓冲区
        self.policy_network.memory.clear()
        
        return {"status": "success", "timestamp": timestamp}
