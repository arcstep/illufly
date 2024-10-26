from typing import List, Union, Optional, Callable, Dict, Generator, AsyncGenerator
from ...utils import raise_invalid_params
from ...io import EventBlock
from .base import Runnable
import inspect
import random

def select_first(consumer_dict: Dict, runnables: List[Runnable]):
    return runnables[0]

def select_random(consumer_dict: Dict, runnables: List[Runnable]):
    """
    从runnables列表中随机选择一个Runnable对象
    """
    if not runnables:
        raise ValueError("runnables列表不能为空")
    return random.choice(runnables)

class End(Runnable):
    @classmethod
    def allowed_params(cls):
        return {
            **Runnable.allowed_params()
        }

    def __init__(self,**kwargs):
        raise_invalid_params(kwargs, self.__class__.allowed_params())

        kwargs.update({"name": "__End__"})
        super().__init__(**kwargs)

        self.description = "我是一个结束标志"

    def call(self, *args, **kwargs):
        pass

class Selector(Runnable):
    """
    路由选择 Runnable 对象的智能体，并将任务分发给被选择对象执行。

    可以根据模型，以及配置模型所需的工具集、资源、数据、handlers等不同参数，构建为不同的智能体对象。

    Selector 需要执行 select 方法来确定选中对象，然后你可以通过 selected 属性来提取选中对象。
    但如果你使用 Selector 的 call 方法，则会自动调用一次 select 方法。

    由于 select 方法不是一个幂等操作，可能两次 select 方法的返回结果并不相同，因此你应当非常小心地管理 select 方法的调用。
    """
    @classmethod
    def allowed_params(cls):
        return {
            "runnables": "参与路由的 Runnable 列表",
            "condition": "选择条件，可以是自定义 Callable 或通过字符串选择内置的条件函数[first, random, similar]。自定义时有三种参数：无参数、仅 consumer_dict 一个参数 或同时提供 consumer_dict 和 runnables 两个参数",
            "embeddings": "如果 condition 是 similar 则需要提供用于相似度计算的 embeddings 实例",
            **Runnable.allowed_params()
        }

    def __init__(
        self,
        condition: Union[Callable, str] = None,
        runnables: List[Runnable] = None,
        embeddings: "BaseEmbeddings" = None,
        **kwargs
    ):
        raise_invalid_params(kwargs, self.__class__.allowed_params())

        super().__init__(**kwargs)

        if runnables:
            self.runnables = runnables if isinstance(runnables, list) else [runnables]
        else:
            self.runnables = []

        if runnables and not all(isinstance(router, Runnable) for router in self.runnables):
            raise ValueError("param runnables must be a list of Runnables")

        self.condition = self.get_condition(condition)
        self.embeddings = embeddings

        for runnable in self.runnables:
            self.bind_consumer(runnable)
        
        self._selected = None

    def get_condition(self, condition):
        default_selected = {
            "first": select_first,
            "random": select_random,
            "similar": self.similar_with_description
        }
        if condition is None:
            return default_selected['first']
        elif isinstance(condition, str):
            return default_selected.get(condition.lower(), default_selected['first'])
        elif isinstance(condition, Callable):
            return condition
        else:
            raise ValueError("param condition must be a Callable")

    @property
    def selected(self):
        if self._selected is None:
            self.select()
        return self._selected

    def select(self):
        """
        selected 可以是一个 Runnable 对象，也可以是一个字符串（表示备选 Runnable 的名称）
        """
        signature = inspect.signature(self.condition)
        if len(signature.parameters) == 0:
            resp = self.condition()
        elif len(signature.parameters) == 1:
            resp = self.condition(self.consumer_dict)
        else:
            resp = self.condition(self.consumer_dict, self.runnables)

        if isinstance(resp, str):
            if resp.lower() == "end":
                self._selected = End()
        self._selected = resp
        return self._selected

    def call(self, *args, **kwargs) -> List[dict]:
        self.select()
        yield from self.selected.call(*args, **kwargs)
        self._last_output = self.selected.last_output

    async def async_call(self, *args, **kwargs) -> List[dict]:
        self.select()
        resp = await self.selected.async_call(*args, **kwargs)
        if isinstance(resp, Generator):
            for block in resp:
                yield block
        elif isinstance(resp, AsyncGenerator):
            async for block in resp:
                yield block
        else:
            yield resp
        self._last_output = resp.last_output

    def similar_with_description(self):
        if not self.embeddings:
            raise ValueError("embeddings is not set")

        from ...community.faiss import FaissDB

        db = FaissDB(embeddings=self.embeddings)
        for run in self.runnables:
            if run.description:
                db.load_text(run.description)

        query = self.consumer_dict.get("task")
        if query:
            results = db(query)
            desc = results[0]
            for run in self.runnables:
                if run.description == desc.text:
                    return run
            raise ValueError(f"router {desc.text} not found in {self.runnables}")
        else:
            return self.runnables[0]
