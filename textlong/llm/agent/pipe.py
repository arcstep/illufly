from .base import Runnable
from ...io import TextBlock
from ...utils import compress_text

class Pipe(Runnable):
    def __init__(self):
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
        last = None
        for run in self.runnables:
            if last and run['prompt']:
                info = f"节点: {compress_text(run['prompt'], 30, 30, 10)}"
                yield TextBlock("info", info)

                _prompt = f"我刚刚已经获得如下内容：\n{last}\n{run['prompt']}"
            else:
                yield TextBlock("info", "智能体管道开始")
                _prompt = prompt
                
            for block in run['runnable'].call(_prompt, *args, **kwargs):
                yield block
            last = run['runnable'].memory[-1]['content']
