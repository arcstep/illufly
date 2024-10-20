import copy
import pandas as pd
import asyncio

from typing import Union, List, Dict, Any, Callable, Generator, AsyncGenerator

from .tool_ability import ToolAbility
from .resource_manager import ResourceManager
from ...dataset import Dataset
from ..base import Runnable
from ....io import EventBlock
from ....utils import filter_kwargs, raise_invalid_params

class BaseAgent(Runnable, ToolAbility, ResourceManager):
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
    @classmethod
    def available_init_params(cls):
        """
        返回当前可用的参数列表。
        """
        return {
            "func": "用于自定义工具的同步执行函数",
            "async_func": "用于自定义工具的异步执行函数",
            **Runnable.available_init_params(),
            **ToolAbility.available_init_params(),
            **ResourceManager.available_init_params(),
        }

    def __init__(
        self,
        func: Callable=None,
        async_func: Callable=None,
        **kwargs
    ):
        raise_invalid_params(kwargs, self.__class__.available_init_params())

        Runnable.__init__(self, **filter_kwargs(kwargs, Runnable.available_init_params()))
        ResourceManager.__init__(self, **filter_kwargs(kwargs, ResourceManager.available_init_params()))

        name = kwargs.pop("name", self.name)
        description = kwargs.pop("description", None)
        _func = func or async_func
        if _func:
            self.name = kwargs.get("name", _func.__name__)
            name = self.name
            description = _func.__doc__ if _func.__doc__ else description
        ToolAbility.__init__(
            self,
            func=func,
            async_func=async_func,
            name=name,
            description=description
        )

    @property
    def runnable_info(self):
        info = super().runnable_info
        info.update({
            "agent_name": self.name,
            "agent_description": self.description,
        })
        return info

    @property
    def provider_dict(self):
        local_dict = {
            "resources": "\n".join(self.get_resources()),
        }
        return {
            **super().provider_dict,
            **{k:v for k,v in local_dict.items() if v is not None},
        }

    def call(self, *args, **kwargs):
        if not isinstance(self.func, Callable):
            raise ValueError("func must be a callable")

        resp = self.func(*args, **kwargs)
        if isinstance(resp, Generator):
            for block in resp:
                if isinstance(block, EventBlock):
                    if block.type == "final_text":
                        self._last_output = block.content
                yield block
        else:
            self._last_output = resp
            yield EventBlock("text", resp)

    async def async_call(self, *args, **kwargs):
        if self.async_func:
            # 使用 asyncio.iscoroutinefunction 判断是否为协程函数
            if asyncio.iscoroutinefunction(self.async_func):
                resp = await self.async_func(*args, **kwargs)
            else:
                resp = self.async_func(*args, **kwargs)
        else:
            resp = self.func(*args, **kwargs)

        if isinstance(resp, Generator):
            for block in resp:
                if isinstance(block, EventBlock):
                    if block.type == "final_text":
                        self._last_output = block.content
                yield block
        elif isinstance(resp, AsyncGenerator):
            async for block in resp:
                if isinstance(block, EventBlock):
                    if block.type == "final_text":
                        self._last_output = block.content
                yield block
        else:
            self._last_output = resp
            yield EventBlock("text", resp)