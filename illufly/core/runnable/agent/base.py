import copy
import pandas as pd

from typing import Union, List, Dict, Any, Callable

from .tool_ability import ToolAbility
from ...dataset import Dataset
from ..base import Runnable

class BaseAgent(Runnable, ToolAbility):
    """    
    基于 BaseAgent 子类可以实现多智能体协作。

    什么时候直接从 BaseAgent 继承？
    - 需要 Runnable 基类的能力的同时
    - 还需要作为工具被使用
    - 例如，多模态模型

    什么时候转而使用ChatAgent？
    - 需要管理记忆、知识、数据等上下文
    - 例如，对话模型
    """

    def __init__(
        self,
        **kwargs
    ):
        Runnable.__init__(self, **kwargs)
        ToolAbility.__init__(self, **kwargs)

    @property
    def runnable_info(self):
        info = super().runnable_info
        info.update({
            "agent_name": self.name,
            "agent_description": self.description,
        })
        return info

