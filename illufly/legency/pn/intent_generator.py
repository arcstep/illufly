import os
import json
import re
import random
import asyncio
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from collections import defaultdict
import traceback

from ..community import ChatOpenAI
from ..community.models import BlockType
from ..prompt import PromptTemplate
from .analyze import analyze_data

class IntentDataGenerator:
    """
    生成用于意图策略网络训练的数据
    包含用户问题和历史意图序列的训练样本
    """
    
    def __init__(
        self, 
        output_dir: str = "intent_data",
        model: str = "qwen-plus",
        imitator: Optional[str] = "QWEN",
        batch_size: int = 5,
        temperature: float = 0.7,
        intent_types: Optional[List[str]] = None,
        max_history_len: int = 5
    ):
        self.output_dir = output_dir
        self.batch_size = batch_size
        self.max_history_len = max_history_len
        
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 初始化LLM客户端
        self.llm = ChatOpenAI(
            model=model,
            imitator=imitator
        )
        self.temperature = temperature
        
        # 设置意图类型
        self.intent_types = intent_types or [
            "查询信息", "获取帮助", "投诉反馈", "预订服务", 
            "取消服务", "支付相关", "账户管理", "技术支持"
        ]
        
        # 默认系统提示词
        self.default_system_prompt = PromptTemplate(text="""
        你是一个数据生成专家，负责创建用于训练意图识别模型的数据。
        
        你需要生成真实、多样化的用户问题样本，并为每个样本分配适当的意图类型。
        每个样本还需要包含合理的历史意图序列，表示用户之前的行为轨迹。
        
        请确保：
        1. 用户问题真实自然，符合日常表达习惯
        2. 问题与分配的意图类型匹配
        3. 历史意图序列合理，能反映出用户可能的行为路径
        4. 数据覆盖各种不同的场景和用例
        
        输出应为JSON格式，包含query(用户问题)、intent(当前意图)和history(历史意图序列)字段。
        """)
        
        # 修改默认用户提示词模板
        self.default_user_prompt = PromptTemplate(text="""
        {{#domain}}针对{{domain}}领域的场景进行生成。{{/domain}} 生成{{count}}个训练样本：

        你生成的 query 是用户的问题，intent 是用户的问题对应的意图类型，history 是用户的问题对应的历史意图序列。
        你生成的数据中 intent 和 history 必须严格从以下列表中选择：
        {{intent_list}}

        {{#intent_distribution}}
        你生成的数据中 intent 的分布比例必须严格遵循以下配置：
        {{intent_distribution}}
        {{/intent_distribution}}
        
        重要说明：你只能使用上述列表中的意图类型，不要创建或使用任何其他意图类型。
        历史记录中的意图也必须从上述列表中选择。
        
        对于每个样本，请提供：
        1. 用户当前的问题查询（与意图类型和历史意图序列具有严格的关联关系）
        2. 该问题对应的意图类型（严格从上述列表中选择）
        3. 一个合理的历史意图序列（0-{{max_history_len}}个，表示用户之前的行为）        
        
        以下是示例格式（注意：实际生成时必须使用上面列出的意图类型）：
        
        ```json
        [
            {
                "query": "我的账户里还有多少钱",
                "intent": "{{first_intent_example}}",  
                "history": []
            },
            {
                "query": "我需要转账给张三",
                "intent": "{{last_intent_example}}",
                "history": ["{{first_intent_example}}"]
            }
        ]
        ```
        
        请生成多样化的样本，包括不同长度的历史序列（包括一些没有历史的样本）。
        """)
    
    async def generate_batch(
        self,
        system_prompt: str,
        user_prompt: str,
        batch_id: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        生成一批训练数据
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词，必须要求以JSON列表返回
            batch_id: 批次ID
            metadata: 可选的元数据，将添加到每个生成的数据项
            
        Returns:
            解析后的数据列表
        """
        # 调用LLM生成数据
        json_text = ""
        try:
            async for x in self.llm.generate(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature
            ):
                if x.block_type == BlockType.TEXT_FINAL:
                    json_text = x.text
                elif x.block_type == BlockType.TEXT_CHUNK:
                    print(x.text, end="")
                else:
                    json_text = str(x)
        except Exception as e:
            print(f"生成数据时出错: {e}")
            traceback.print_exc()
            return []
        
        # 解析响应JSON
        return self._parse_json_response(json_text, batch_id, metadata)
    
    def _parse_json_response(
        self,
        text: str,
        batch_id: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """解析JSON响应，增强错误处理"""
        if not text:
            print("生成的文本为空")
            return []
        
        try:
            # 提取JSON部分
            pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
            match = re.search(pattern, text)
            if match:
                json_text = match.group(1).strip()
            else:
                # 尝试寻找JSON数组
                array_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', text)
                if array_match:
                    json_text = array_match.group(0)
                else:
                    json_text = text
            
            # 替换Python风格的单引号为双引号
            json_text = re.sub(r"'([^']*?)': ", r'"\1": ', json_text)
            json_text = re.sub(r"'([^']*?)'", r'"\1"', json_text)
            
            # 简化JSON，移除尾部逗号
            json_text = re.sub(r',\s*}', '}', json_text)
            json_text = re.sub(r',\s*]', ']', json_text)
            
            # 尝试解析
            try:
                data = json.loads(json_text)
                print("JSON解析成功")
            except json.JSONDecodeError as e:
                print(f"JSON解析错误: {e}")
                # 保存问题JSON以便调试
                debug_file = f"debug_json_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(f"原始响应:\n{text}\n\n处理后文本:\n{json_text}")
                print(f"已保存调试信息到 {debug_file}")
                return []
            
            # 确保数据是列表格式
            if not isinstance(data, list):
                if isinstance(data, dict):
                    # 尝试查找列表字段
                    for key in ['samples', 'data', 'results', 'items']:
                        if key in data and isinstance(data[key], list):
                            data = data[key]
                            break
                    else:
                        data = [data]
                else:
                    data = [data]
            
            # 验证和净化数据
            validated_data = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                
                # 确保必要字段存在
                if "query" not in item or "intent" not in item:
                    continue
                
                # 确保intent是有效的
                if item["intent"] not in self.intent_types:
                    # 尝试匹配最接近的意图类型
                    most_similar = self._find_closest_intent(item["intent"])
                    if most_similar:
                        item["intent"] = most_similar
                    else:
                        continue  # 跳过无效意图
                
                # 确保history是列表
                if "history" not in item:
                    item["history"] = []
                elif not isinstance(item["history"], list):
                    item["history"] = []
                
                # 净化历史记录中的意图
                valid_history = []
                for h_intent in item["history"]:
                    if h_intent in self.intent_types:
                        valid_history.append(h_intent)
                    else:
                        # 尝试匹配最接近的意图类型
                        most_similar = self._find_closest_intent(h_intent)
                        if most_similar:
                            valid_history.append(most_similar)
                
                # 限制历史长度
                item["history"] = valid_history[-self.max_history_len:]
                
                # 添加元数据
                item['batch_id'] = batch_id
                item['timestamp'] = datetime.now().isoformat()
                if metadata:
                    for key, value in metadata.items():
                        item[key] = value
                
                validated_data.append(item)
            
            return validated_data
            
        except Exception as e:
            print(f"处理JSON响应时出错: {e}")
            traceback.print_exc()
            return []
    
    def _find_closest_intent(self, intent: str) -> Optional[str]:
        """找到最接近的有效意图类型"""
        # 简单的字符串匹配，可以根据需要改进为更复杂的算法
        intent_lower = intent.lower()
        for valid_intent in self.intent_types:
            if valid_intent.lower() in intent_lower or intent_lower in valid_intent.lower():
                return valid_intent
        return None
    
    async def generate_intent_data(
        self,
        domains: Optional[List[str]] = None,
        system_prompt: Optional[Union[str, PromptTemplate]] = None,
        user_prompt_template: Optional[Union[str, PromptTemplate]] = None,
        num_batches: Optional[int] = None,
        intent_distribution: Optional[Dict[str, float]] = None,
        vary_history_length: bool = True
    ) -> List[Dict[str, Any]]:
        """
        生成意图识别训练数据
        
        Args:
            domains: 可选的领域列表，每个批次将使用一个领域
            system_prompt: 系统提示词，默认使用内置模板
            user_prompt_template: 用户提示词模板，默认使用内置模板
            num_batches: 批次数量，默认为1或domains长度
            intent_distribution: 意图分布配置，如{"查询信息": 0.3, "预订服务": 0.2}
            vary_history_length: 是否生成不同长度的历史序列
            
        Returns:
            生成的训练数据列表
        """
        # 设置批次数和领域
        if domains:
            domain_batches = domains
            if num_batches and num_batches > len(domains):
                # 如果批次数大于领域数，循环使用领域
                domain_batches = domains * (num_batches // len(domains))
                domain_batches += domains[:num_batches % len(domains)]
            num_batches = len(domain_batches)
        else:
            domain_batches = [None] * (num_batches or 1)
            num_batches = len(domain_batches)
        
        # 使用默认提示词或传入的提示词
        sys_prompt = system_prompt or self.default_system_prompt
        user_prompt = user_prompt_template or self.default_user_prompt
        
        # 准备意图类型字符串
        intent_types_str = "\n".join([f"- {intent}" for intent in self.intent_types])
        
        # 准备批次元数据
        batch_metadata = []
        for i, domain in enumerate(domain_batches):
            metadata = {"batch_id": i+1}
            if domain:
                metadata["domain"] = domain
            
            # 如果指定了意图分布，添加到元数据
            if intent_distribution:
                metadata["intent_distribution"] = intent_distribution
                
            # 如果需要变化历史长度，为每个批次指定不同的偏好
            if vary_history_length:
                # 随机分配历史长度偏好
                history_pref = random.choice([
                    "prefer_short",   # 偏好短历史
                    "prefer_long",    # 偏好长历史
                    "prefer_none",    # 偏好无历史
                    "balanced"        # 平衡分配
                ])
                metadata["history_preference"] = history_pref
                
            batch_metadata.append(metadata)
        
        # 使用时间戳生成唯一输出文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = os.path.join(self.output_dir, f"intent_data_{timestamp}.json")
        
        print(f"开始生成意图训练数据，将保存到: {output_file}")
        
        # 生成所有批次数据
        all_data = []
        for i, metadata in enumerate(batch_metadata):
            # 构建变量映射
            variables = {
                "count": self.batch_size,
                "intent_types": intent_types_str,
                "max_history_len": self.max_history_len,
                "intent_list": self.intent_types,
                "first_intent_example": self.intent_types[0],
                "last_intent_example": self.intent_types[-1]                
            }
            
            # 添加领域信息
            if "domain" in metadata:
                variables["domain"] = metadata["domain"]
                
            # 添加意图分布
            if "intent_distribution" in metadata:
                dist_str = ", ".join([f"{k}: {v:.1%}" for k, v in metadata["intent_distribution"].items()])
                variables["intent_distribution"] = f"{dist_str}"

            # 添加历史长度偏好
            if "history_preference" in metadata:
                pref = metadata["history_preference"]
                if pref == "prefer_short":
                    variables["history_note"] = "大多数样本应有1-2条历史记录。"
                elif pref == "prefer_long":
                    variables["history_note"] = f"大多数样本应有3-{self.max_history_len}条历史记录。"
                elif pref == "prefer_none":
                    variables["history_note"] = "大约一半样本应没有历史记录。"
                else:
                    variables["history_note"] = "历史记录长度应均衡分布。"
            
            # 格式化提示词
            formatted_sys = sys_prompt
            if isinstance(sys_prompt, PromptTemplate):
                formatted_sys = sys_prompt.format(variables)
                
            formatted_user = user_prompt
            if isinstance(user_prompt, PromptTemplate):
                formatted_user = user_prompt.format(variables)
            
            print(formatted_user)
            
            # 生成批次数据
            print(f"\n===== 生成批次 {i+1}/{num_batches} =====")
            if "domain" in metadata:
                print(f"领域: {metadata['domain']}")
            if "history_preference" in metadata:
                print(f"历史长度偏好: {metadata['history_preference']}")
                
            batch_data = await self.generate_batch(
                formatted_sys,
                formatted_user,
                i+1,
                metadata
            )
            
            if batch_data:
                all_data.extend(batch_data)
                print(f"批次 {i+1} 完成: 获取到 {len(batch_data)} 条数据")
                
                # 保存当前所有数据
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(all_data, f, ensure_ascii=False, indent=2)
                print(f"已更新数据文件，当前共 {len(all_data)} 条数据")
            else:
                print(f"批次 {i+1} 未生成有效数据")
            
            # 添加延迟以避免API限制
            if i < num_batches - 1:
                await asyncio.sleep(1)
        
        # 生成完成，保存并分析
        if all_data:
            # 分析数据
            report = self.analyze_intent_data(all_data)
            print("\n===== 意图数据分析报告 =====")
            print(report)
            
            # 保存分析报告
            report_file = os.path.join(self.output_dir, f"intent_report_{timestamp}.txt")
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"分析报告已保存到: {report_file}")
        
        return all_data
    
    def analyze_intent_data(self, data: List[Dict[str, Any]]) -> str:
        """分析意图数据集的特征"""
        if not data:
            return "无数据可分析"
        
        # 基本统计
        total = len(data)
        intent_counts = defaultdict(int)
        history_length_counts = defaultdict(int)
        domain_counts = defaultdict(int)
        query_lengths = []
        
        # 历史意图转换统计
        transitions = defaultdict(lambda: defaultdict(int))
        
        # 统计数据
        for item in data:
            # 统计当前意图
            intent = item.get("intent", "未知")
            intent_counts[intent] += 1
            
            # 统计历史长度
            history = item.get("history", [])
            history_length_counts[len(history)] += 1
            
            # 统计领域
            if "domain" in item:
                domain_counts[item["domain"]] += 1
                
            # 统计查询长度
            if "query" in item:
                query_lengths.append(len(item["query"]))
                
            # 统计历史意图转换
            if history:
                # 统计从历史最后一个意图到当前意图的转换
                last_intent = history[-1]
                transitions[last_intent][intent] += 1
        
        # 生成报告
        report_lines = []
        report_lines.append(f"意图训练数据分析 - 总样本数: {total}")
        report_lines.append("=" * 50)
        
        # 意图分布
        report_lines.append("\n意图分布:")
        for intent, count in sorted(intent_counts.items(), key=lambda x: -x[1]):
            percent = (count / total) * 100
            bar = "#" * int(percent / 5)
            report_lines.append(f"  {intent}: {count} ({percent:.1f}%) {bar}")
        
        # 历史长度分布
        report_lines.append("\n历史长度分布:")
        for length in range(self.max_history_len + 1):
            count = history_length_counts.get(length, 0)
            percent = (count / total) * 100
            bar = "#" * int(percent / 5)
            report_lines.append(f"  长度 {length}: {count} ({percent:.1f}%) {bar}")
        
        # 领域分布（如果有）
        if domain_counts:
            report_lines.append("\n领域分布:")
            for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
                percent = (count / total) * 100
                bar = "#" * int(percent / 5)
                report_lines.append(f"  {domain}: {count} ({percent:.1f}%) {bar}")
        
        # 查询长度统计
        if query_lengths:
            avg_length = sum(query_lengths) / len(query_lengths)
            min_length = min(query_lengths)
            max_length = max(query_lengths)
            report_lines.append(f"\n查询长度统计:")
            report_lines.append(f"  最小长度: {min_length} 字符")
            report_lines.append(f"  最大长度: {max_length} 字符")
            report_lines.append(f"  平均长度: {avg_length:.1f} 字符")
        
        # 意图转换分析（Top-3）
        report_lines.append("\n意图转换分析 (前3高频):")
        for from_intent in sorted(transitions.keys()):
            transitions_from = transitions[from_intent]
            report_lines.append(f"  从 '{from_intent}' 转换到:")
            
            # 对该起始意图的所有转换进行排序，并取Top-3
            top_transitions = sorted(transitions_from.items(), key=lambda x: -x[1])[:3]
            for to_intent, count in top_transitions:
                total_from = sum(transitions_from.values())
                percent = (count / total_from) * 100
                report_lines.append(f"    -> '{to_intent}': {count} ({percent:.1f}%)")
        
        return "\n".join(report_lines)
    
    @staticmethod
    def filter_by_intent(data: List[Dict[str, Any]], intent: str) -> List[Dict[str, Any]]:
        """筛选特定意图的训练样本"""
        return [item for item in data if item.get("intent") == intent]
    
    @staticmethod
    def filter_by_history_length(data: List[Dict[str, Any]], length: int) -> List[Dict[str, Any]]:
        """筛选特定历史长度的训练样本"""
        return [item for item in data if len(item.get("history", [])) == length]
    
    @staticmethod
    def split_train_val(
        data: List[Dict[str, Any]], val_ratio: float = 0.2, 
        balance_intents: bool = True, seed: int = 42
    ) -> tuple:
        """
        将数据集拆分为训练集和验证集
        
        Args:
            data: 完整数据集
            val_ratio: 验证集比例
            balance_intents: 是否平衡各意图在训练集和验证集中的分布
            seed: 随机种子
            
        Returns:
            (训练集, 验证集)元组
        """
        random.seed(seed)
        
        if not balance_intents:
            # 简单随机拆分
            indices = list(range(len(data)))
            random.shuffle(indices)
            split_idx = int(len(data) * (1 - val_ratio))
            train_indices = indices[:split_idx]
            val_indices = indices[split_idx:]
            
            train_data = [data[i] for i in train_indices]
            val_data = [data[i] for i in val_indices]
            return train_data, val_data
        
        # 按意图分组
        intent_groups = defaultdict(list)
        for i, item in enumerate(data):
            intent = item.get("intent", "unknown")
            intent_groups[intent].append(i)
        
        # 分别从每个意图组中选取验证集
        train_indices = []
        val_indices = []
        
        for intent, indices in intent_groups.items():
            random.shuffle(indices)
            split_idx = int(len(indices) * (1 - val_ratio))
            train_indices.extend(indices[:split_idx])
            val_indices.extend(indices[split_idx:])
        
        # 返回结果
        train_data = [data[i] for i in train_indices]
        val_data = [data[i] for i in val_indices]
        return train_data, val_data
