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
    def __init__(self, *runnables):
        """ 
        快速构造智能体运行管道
        """
        super().__init__("PIPE")
        self.runnables = runnables

    def __str__(self):
        runnable_types = [type(run).__name__ for run in self.runnables]
        return f"Pipe({runnable_types})"
    
    def __repr__(self):
        runnable_types = [type(run).__name__ for run in self.runnables]
        return f"Pipe({runnable_types})"

    def call(self, *args, **kwargs):
        """
        执行智能体管道。
        """
        prev_runnable = None
        for index, run in enumerate(self.runnables):
            info = self._get_node_info(index + 1, run)
            yield TextBlock("info", info)
            if index == 0:
                current_args = args
                current_kwargs = kwargs
            else:
                if isinstance(prev_runnable, Template):
                    prompt = prev_runnable.memory
                else:
                    prompt = prev_runnable.output
                current_args = [prompt]
                current_kwargs = {}

            self.create_new_memory(f"节点 <{index}> 正在处理任务...")
            for block in run.call(*current_args, **current_kwargs):
                yield block
            self.remember_response(run.output)
            prev_runnable = run

    def _get_node_info(self, index, run):
        if isinstance(run, ChatAgent):
            if run.system_prompt:
                info = f">>> Node {index}: {compress_text(run.system_prompt, 30, 30, 10)}"
            else:
                info = f">>> Node {index}: {run.__class__.__name__}"
        else:
            info = f">>> Node {index}: {run.__class__.__name__}"
        return info
