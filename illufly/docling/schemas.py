"""文档处理数据模型

包含文档处理过程中使用的数据模型、枚举和类型定义
"""

from enum import Enum
from typing import Dict, Any, Optional, List, Union
import datetime


class DocumentProcessStage(str, Enum):
    """文档处理阶段枚举"""
    INIT = "INIT"  # 初始化
    DOWNLOADING = "DOWNLOADING"  # 下载中
    PROCESSING = "PROCESSING"  # 处理中
    BUILD = "BUILD"  # 构建中
    ASSEMBLE = "ASSEMBLE"  # 组装中
    ENRICH = "ENRICH"  # 丰富内容中
    CHUNKING = "CHUNKING"  # 文档分块中
    COMPLETE = "COMPLETE"  # 完成
    ERROR = "ERROR"  # 错误


class DocumentProcessStatus:
    """文档处理状态类
    
    跟踪文档处理的进度、当前阶段和消息
    """
    def __init__(self, doc_id: str, user_id: Optional[str] = None):
        self.doc_id = doc_id
        self.user_id = user_id  # 可选参数，兼容旧代码
        self.stage: DocumentProcessStage = DocumentProcessStage.INIT
        self.progress: float = 0.0
        self.messages: List[str] = []
        self.start_time = datetime.datetime.now()
        self.end_time: Optional[datetime.datetime] = None
        self.intermediate_results: Dict[str, Any] = {}
        self.error: Optional[str] = None
        self.cancelled: bool = False
    
    def update(self, stage: Optional[DocumentProcessStage] = None, 
              progress: Optional[float] = None,
              message: Optional[str] = None,
              error: Optional[str] = None) -> None:
        """更新处理状态
        
        Args:
            stage: 文档处理阶段
            progress: 处理进度 (0.0-1.0)
            message: 状态消息
            error: 错误信息
        """
        if stage is not None:
            self.stage = stage
        
        if progress is not None:
            self.progress = max(0.0, min(1.0, progress))
        
        if message is not None:
            self.messages.append(message)
        
        if error is not None:
            self.error = error
            self.stage = DocumentProcessStage.ERROR
        
        # 如果进度为1.0且阶段不是ERROR，则更新为COMPLETE
        if self.progress >= 1.0 and self.stage != DocumentProcessStage.ERROR:
            self.stage = DocumentProcessStage.COMPLETE
            self.end_time = datetime.datetime.now()
    
    # 为兼容性添加旧方法
    def complete(self, message: str = "处理完成") -> 'DocumentProcessStatus':
        """标记为完成状态（兼容旧版）"""
        self.update(stage=DocumentProcessStage.COMPLETE, progress=1.0, message=message)
        return self
    
    def fail(self, error: str) -> 'DocumentProcessStatus':
        """标记为失败状态（兼容旧版）"""
        self.update(stage=DocumentProcessStage.ERROR, progress=0.0, message=f"处理失败: {error}", error=error)
        return self
    
    def cancel(self) -> bool:
        """取消处理（兼容旧版）"""
        self.cancelled = True
        self.update(stage=DocumentProcessStage.ERROR, progress=0.0, message="用户取消处理")
        return True
    
    @property
    def message(self) -> str:
        """获取最新消息（兼容旧版）"""
        return self.messages[-1] if self.messages else ""
    
    @property
    def duration(self) -> float:
        """获取处理持续时间（秒）"""
        end = self.end_time or datetime.datetime.now()
        return (end - self.start_time).total_seconds()
    
    @property
    def cancellable(self) -> bool:
        """是否可取消（兼容旧版）"""
        return self.stage not in [DocumentProcessStage.COMPLETE, DocumentProcessStage.ERROR]
    
    def to_dict(self) -> Dict[str, Any]:
        """将状态转换为字典"""
        result = {
            "doc_id": self.doc_id,
            "stage": self.stage.value,
            "progress": self.progress,
            "messages": self.messages,
            "message": self.message,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "error": self.error,
            "cancelled": self.cancelled
        }
        if self.user_id:
            result["user_id"] = self.user_id
        return result
    
    def model_dump(self) -> Dict[str, Any]:
        """兼容pydantic接口"""
        return self.to_dict()

