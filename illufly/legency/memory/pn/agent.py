
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

from .base import PolicyNetwork, LLMInterface

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
            source = "llm"
            
        # 准备结果
        return {
            "action_type": action_type,
            "action_name": self.policy_network.action_names[action_type],
            "action_params": action_params,
            "source": source,
            "all_probabilities": prediction.probabilities
        }
    
