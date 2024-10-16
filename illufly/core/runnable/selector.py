from typing import List, Union, Optional, Callable, Dict, Generator, AsyncGenerator
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
    def __init__(self, *args, **kwargs):
        kwargs.update({"name": "__End__"})
        super().__init__(*args, **kwargs)

        self.description = "我是一个结束标志"

    def call(*args, **kwargs):
        pass

class Selector(Runnable):
    """
    路由选择 Runnable 对象的智能体，并将任务分发给被选择对象执行。

    可以根据模型，以及配置模型所需的工具集、资源、数据、handlers等不同参数，构建为不同的智能体对象。
    """
    def __init__(
        self,
        runnables: List[Runnable] = None,
        condition: Union[Callable, str] = None,
        embeddings: "BaseEmbeddings" = None,
        **kwargs
    ):
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

    def get_condition(self, condition):
        default_selected = {
            "first": select_first,
            "random": select_random,
            "similar": self.select_with_description
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
                return End()
        return resp

    def reset(self):
        for runnable in self.runnables:
            runnable.reset()

    def call(self, *args, **kwargs) -> List[dict]:
        yield from self.selected.call(*args, **kwargs)

    async def async_call(self, *args, **kwargs) -> List[dict]:
        resp = self.selected.async_call(*args, **kwargs)
        if isinstance(resp, Generator):
            for block in resp:
                yield block
        elif isinstance(resp, AsyncGenerator):
            async for block in resp:
                yield block
        else:
            yield resp

    def select_with_description(self, runnables: List[Runnable], consumer_dict: Dict):
        if not self.embeddings:
            raise ValueError("embeddings is not set")

        from ...community.faiss import FaissDB

        db = FaissDB(embeddings=self.embeddings)
        for run in runnables:
            if run.description:
                db.load_text(run.description)

        query = consumer_dict.get("task")
        if query:
            results = db(query)
            desc = results[0]
            for run in runnables:
                if run.description == desc.text:
                    return run
            raise ValueError(f"router {desc.text} not found in {runnables}")
        else:
            return runnables[0]
