from enum import Enum

class MemoryType(str, Enum):
    """记忆类型"""
    THREAD = "thread"
    QA = "QA"
    FACT = "fact"
    CONCEPT = "concept"
    THEMATIC_GRAPH = "thematic_graph"
    CORE_VIEW = "core_view"

class TaskState(str, Enum):
    """任务状态"""
    TODO = "todo"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"
