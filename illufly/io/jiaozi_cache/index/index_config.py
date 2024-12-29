from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class IndexUpdateStrategy(str, Enum):
    """索引更新策略"""
    SYNC = "sync"      # 同步更新
    ASYNC = "async"    # 异步更新
    BATCH = "batch"    # 批量更新

class IndexConfig(BaseModel):
    """索引配置类
    
    使用 Pydantic 管理索引配置，提供:
    - 自动类型转换
    - 配置验证
    - JSON 序列化
    - 模型继承
    """
    
    update_strategy: IndexUpdateStrategy = Field(
        default=IndexUpdateStrategy.SYNC,
        description="索引更新策略"
    )
    
    cache_size: int = Field(
        default=1000,
        ge=0,
        description="索引缓存大小"
    )
    
    cache_ttl: int = Field(
        default=3600,
        ge=0,
        description="缓存过期时间(秒)"
    )
    
    enable_stats: bool = Field(
        default=True,
        description="是否启用统计"
    )
    
    error_threshold: int = Field(
        default=100,
        ge=0,
        description="错误阈值"
    )
    
    class Config:
        use_enum_values = True 