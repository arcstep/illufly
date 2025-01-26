from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

class Concept(BaseModel):
    """L2: 概念节点

    概念节点，通常用于保存一个 thread_id 的所有概念节点。
    概念节点是基于一次对话的概念认知梳理，是用户认知管理中最核心的结构。
    """
    concept_id: str
    concept_name: str
    description: str
    related_facts: List[str] = Field(default_factory=list)  # 关联的事实摘要ID
    relations: Dict[str, List[str]] = Field(
        default_factory=dict, 
        description="与其他概念的关系：{关系类型: [概念ID]}"
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evolution: List[Dict] = Field(
        default_factory=list,
        description="概念认知的演化历史"
    )

    def model_dump(self, **kwargs) -> Dict[str, Any]:
        """自定义序列化方法"""
        return {
            "concept_id": self.concept_id,
            "concept_name": self.concept_name,
            "description": self.description,
            "related_facts": self.related_facts,
            "relations": self.relations,
            "confidence": self.confidence,
            "evolution": self.evolution
        }

    @classmethod
    def model_validate(cls, obj: Dict[str, Any]) -> "Concept":
        """自定义反序列化方法"""
        if isinstance(obj, dict):
            # 处理简化的概念数据
            if "id" in obj and "name" in obj:
                return cls(
                    concept_id=obj["id"],
                    concept_name=obj["name"],
                    description=obj.get("description", f"概念：{obj['name']}"),
                    related_facts=obj.get("related_facts", []),
                    relations=obj.get("relations", {}),
                    confidence=obj.get("confidence", 1.0),
                    evolution=obj.get("evolution", [])
                )
        return super().model_validate(obj)
