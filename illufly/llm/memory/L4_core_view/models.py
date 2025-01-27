from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import datetime

class CoreView(BaseModel):
    """L4: 中心观点

    每个中心观点对应一个概念图，每个概念图可产生多个中心观点。
    中心观点是对概念图的特定场景解释，是基于概念图特定路径的看法。
    """
    user_id: str = Field(..., description="用户ID")
    thread_id: str = Field(..., description="对话ID")
    view_id: str = Field(..., description="中心观点ID")
    theme_id: str = Field(..., description="关联的主题ID")
    statement: str = Field(..., description="观点陈述，对概念图做")
    scope: Dict = Field(..., description="适用范围")
    dependencies: List[str] = Field(
        default_factory=list,
        description="依赖的其他观点ID"
    )
    valid_until: Optional[datetime] = None

