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
        runnable_types = [type(run['runnable']).__name__ for run in [self.start_runnable] + self.to_runnables]
        return f"Pipe({runnable_types})"
    
    def __repr__(self):
        runnable_types = [type(run['runnable']).__name__ for run in [self.start_runnable] + self.to_runnables]
        return f"Pipe({runnable_types})"

    def start(self, run: Runnable):
        self.start_runnable = {
            "runnable": run,
            "prompt": None,
        }

    def to(self, run: Runnable, prompt: str):
        self.to_runnables.append(
            {
                "runnable": run,
                "prompt": prompt,
            }
        )

    def call(self, *args, **kwargs):
        """
        执行智能体管道。

        可以包含各种组合，例如：

        1. 多个智能体首尾相连
        [prompt] --> ChatAgent --> [output] --> [messages] --> ChatAgent

        2. 从提示语模板开始构造管道序列
        [input] --> Template --> [output] --> [messages] --> ChatAgent

        3. 提示语模板被嵌入在中间，用于连接两个智能体
        [prompt] --> ChatAgent --> [output] --> [input] --> Template --> ChatAgent

        4. 从一个管道开始，连接到一个对话智能体
        [prompt] --> Pipe --> [output] --> [messages] --> ChatAgent

        4. 管道被嵌入在中间，用于连接两个智能体
        [prompt] --> ChatAgent --> [output] --> [messages] --> Pipe --> ChatAgent
        """
        all_runnables = [self.start_runnable] + self.to_runnables
        prev_runnable = None
        for index, run in enumerate(all_runnables):
            if index == 0:
                yield TextBlock("info", ">>> PIPE <{index}> : START")
                current_args = args
                current_kwargs = kwargs
            else:
                info = f">>> PIPE <{index}> : {compress_text(run.get('prompt', ''), 30, 30, 10)}"
                yield TextBlock("info", info)
                if isinstance(prev_runnable, ChatAgent):
                    prompt = f'已知: {self.output}\n {run.get("prompt", "请你评论")}'
                elif isinstance(prev_runnable, Template):
                    prompt = prev_runnable.memory
                else:
                    prompt = self.output
                current_args = [prompt]
                current_kwargs = {}

            self.create_new_memory(f"请节点 <{index}> 处理任务")
            for block in run['runnable'].call(*current_args, **current_kwargs):
                yield block
            self.remember_response(run['runnable'].output)
            prev_runnable = run['runnable']
