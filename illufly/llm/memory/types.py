from enum import Enum

class MemoryType(str, Enum):
    """记忆类型"""
    THREAD = "thread"
    DIALOGUE = "dialogue"
    FACT = "fact"
    CONCEPT = "concept"
    THEMATIC_GRAPH = "thematic_graph"
    CORE_VIEW = "core_view"
