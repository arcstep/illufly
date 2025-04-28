"""文档处理状态相关类"""
from enum import Enum, auto
from typing import List, Dict, Any, Optional, Literal

class DocumentStatus(str, Enum):
    """文档状态枚举"""
    ACTIVE = "active"      # 活跃状态，可用
    DELETED = "deleted"    # 已删除
    PROCESSING = "processing"  # 处理中（任何处理阶段）

class ProcessStage(str, Enum):
    """文档处理阶段枚举"""
    # 主要处理阶段
    READY = "ready"              # 原始文件就绪（已上传或已记录链接）
    CONVERTED = "converted"      # 已完成MD转换
    CHUNKED = "chunked"          # 已完成切片
    EMBEDDED = "embedded"        # 已完成文本嵌入
    
    # 处理中状态
    CONVERTING = "converting"    # MD转换中
    CHUNKING = "chunking"        # 切片中
    EMBEDDING = "embedding"      # 文本嵌入中
    
    # 其他状态
    FAILED = "failed"            # 处理失败
    
    @classmethod
    def get_processing_stages(cls) -> List[str]:
        """获取所有处理中的状态"""
        return [cls.CONVERTING, cls.CHUNKING, cls.EMBEDDING]
    
    @classmethod
    def get_completed_stages(cls) -> List[str]:
        """获取所有已完成的状态"""
        return [cls.CONVERTED, cls.CHUNKED, cls.EMBEDDED]
    
    @classmethod
    def get_next_stage(cls, current_stage: str) -> Optional[str]:
        """获取当前阶段的下一个阶段"""
        stage_sequence = [cls.READY, cls.CONVERTED, cls.CHUNKED, cls.EMBEDDED]
        try:
            current_index = stage_sequence.index(current_stage)
            if current_index < len(stage_sequence) - 1:
                return stage_sequence[current_index + 1]
        except ValueError:
            pass
        return None
    
    @classmethod
    def get_processing_stage(cls, completed_stage: str) -> Optional[str]:
        """获取完成阶段对应的处理中状态"""
        stage_map = {
            cls.CONVERTED: cls.CONVERTING,
            cls.CHUNKED: cls.CHUNKING,
            cls.EMBEDDED: cls.EMBEDDING
        }
        return stage_map.get(completed_stage)
        
    @classmethod
    def get_completed_stage(cls, processing_stage: str) -> Optional[str]:
        """获取处理中状态对应的完成阶段"""
        stage_map = {
            cls.CONVERTING: cls.CONVERTED,
            cls.CHUNKING: cls.CHUNKED,
            cls.EMBEDDING: cls.EMBEDDED
        }
        return stage_map.get(processing_stage)

class DocumentProcessInfo:
    """文档处理信息类"""
    def __init__(self, current_stage: str = ProcessStage.READY):
        self.current_stage = current_stage
        self.stages = {
            "conversion": {
                "stage": ProcessStage.READY,
                "success": False,
                "started_at": None,
                "finished_at": None
            },
            "chunking": {
                "stage": ProcessStage.READY,
                "success": False,
                "started_at": None,
                "finished_at": None
            },
            "embedding": {
                "stage": ProcessStage.READY,
                "success": False,
                "started_at": None,
                "finished_at": None
            }
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "current_stage": self.current_stage,
            "stages": self.stages
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DocumentProcessInfo':
        """从字典创建实例"""
        instance = cls()
        instance.current_stage = data.get("current_stage", ProcessStage.READY)
        instance.stages = data.get("stages", instance.stages)
        return instance
    
    def update_stage(self, 
                     stage_name: Literal["conversion", "chunking", "embedding"], 
                     stage_data: Dict[str, Any]) -> None:
        """更新阶段状态"""
        if stage_name not in self.stages:
            return
        
        # 更新指定阶段
        self.stages[stage_name].update(stage_data)
        
        # 如果指定了新阶段，更新当前阶段
        if "stage" in stage_data:
            self.current_stage = stage_data["stage"]
