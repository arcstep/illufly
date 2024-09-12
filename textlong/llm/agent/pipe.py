from typing import List, Union
from .base import Runnable
from ...io import TextBlock
from ...utils import compress_text
from .chat import ChatAgent
from .template import Template

class Pipe(Runnable):
    """
    智能体管道，用于将多个智能体节点连接起来，形成一个智能体管道。

    Pipe 是 Runnable 的子类，因此可以作为 Runnable 使用。
    """
    def __init__(self, runnables: List[Union[Runnable, tuple]]=[]):
        """ 
        快速构造智能体运行管道
        """
        super().__init__("PIPE")
        self.start_runnable = None
        self.to_runnables = []

        if len(runnables) > 0:
            self.start(runnables[0])
            for run in runnables[1:]:
                if isinstance(run, tuple):
                    self.to(run[0], run[1])
                else:
                    self.to(run, None)

    def __str__(self):
        runnable_types = [type(run).__name__ for run in [self.start_runnable] + self.to_runnables]
        return f"Pipe({runnable_types})"
    
    def __repr__(self):
        runnable_types = [type(run).__name__ for run in [self.start_runnable] + self.to_runnables]
        return f"Pipe({runnable_types})"

    def start(self, run: Runnable):
        self.start_runnable = run

    def to(self, run: Runnable, prompt: str):
        self.to_runnables.append(run)

    def call(self, *args, **kwargs):
        """
        执行智能体管道。
        """
        all_runnables = [self.start_runnable] + self.to_runnables
        prev_runnable = None
        for index, run in enumerate(all_runnables):
            if index == 0:
                yield TextBlock("info", f">>> PIPE <{index}> : START")
                current_args = args
                current_kwargs = kwargs
            else:
                info = f">>> PIPE <{index}> : {compress_text(run.system_prompt, 30, 30, 10)}"
                yield TextBlock("info", info)
                if isinstance(prev_runnable, Template):
                    prompt = prev_runnable.memory
                else:
                    prompt = prev_runnable.output
                current_args = [prompt]
                current_kwargs = {}

            self.create_new_memory(f"请节点 <{index}> 处理任务")
            for block in run.call(*current_args, **current_kwargs):
                yield block
            self.remember_response(run.output)
            prev_runnable = run
