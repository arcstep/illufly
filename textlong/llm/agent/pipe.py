from .base import Runnable
from ...io import TextBlock
from ...utils import compress_text

class Pipe(Runnable):
    """
    智能体管道，用于将多个智能体节点连接起来，形成一个智能体管道。

    Pipe 是 Runnable 的子类，因此可以作为 Runnable 使用。
    """
    def __init__(self):
        super().__init__("PIPE")
        self.runnables = []

    def start(self, run: Runnable):
        self.runnables.append(
            {
                "runnable": run,
                "prompt": None
            }
        )

    def to(self, run: Runnable, prompt: str):
        self.runnables.append(
            {
                "runnable": run,
                "prompt": prompt
            }
        )

    def call(self, prompt: str, *args, **kwargs):
        for index, run in enumerate(self.runnables):
            if index == 0:
                yield TextBlock("info", "智能体管道开始")
                _prompt = prompt
            else:
                info = f"节点: {compress_text(run['prompt'], 30, 30, 10)}"
                yield TextBlock("info", info)
                _prompt = f"我刚刚已经获得如下内容：\n{self.output}\n{run['prompt']}"

            self.create_new_memory(_prompt)
            for block in run['runnable'].call(_prompt, *args, **kwargs):
                yield block
            self.remember_response(run['runnable'].output)
