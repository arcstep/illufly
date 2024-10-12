from typing import List, Union, Optional, Callable, Dict, Generator, AsyncGenerator
from ...io import EventBlock
from .base import Runnable
import inspect


def select_first(runnables: List[Runnable], consumer_dict: Dict):
    return runnables[0]

def select_random(runnables: List[Runnable], consumer_dict: Dict):
    return random.choice(runnables)

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

        self.runnables = runnables if isinstance(runnables, list) else [runnables]
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
            "desc": self.select_with_description
        }
        if condition is None:
            return default_selected['first']
        elif isinstance(condition, str):
            return default_selected.get(condition, default_selected['first'])
        elif isinstance(condition, Callable):
            # 使用 inspect 模块获取函数签名
            signature = inspect.signature(condition)
            if len(signature.parameters) == 0:
                raise ValueError("param condition must have at least one parameter")
            return condition
        else:
            raise ValueError("param condition must be a Callable")

    @property
    def selected(self):
        selected = self.condition(self.runnables, self.consumer_dict)
        if isinstance(selected, Runnable):
            return selected
        elif isinstance(selected, str):
            for run in self.runnables:
                if selected.lower() in run.name.lower():
                    return run

            runnable_names = [r.name for r in self.runnables]
            raise ValueError(f"router {selected} not found in {runnable_names}")

        raise ValueError("selected runnable must be a str(runnable's name) or Runnable object", selected)

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
