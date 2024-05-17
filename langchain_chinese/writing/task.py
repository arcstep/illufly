from typing import Any, Dict, Iterator, List, Optional, Union, Tuple
from .tree import ContentTree
from .command import BaseCommand

class WritingTask(BaseCommand):
    """
    长文写作任务。
    """

    def __init__(self):
        self.human_input = lambda x : x if x != None else input("\n👤: ")
        self.tree = ContentTree()

    # inherit
    @property
    def default_command(self) -> str:
        return self.tree.default_command

    # inherit
    @property
    def commands(self) -> List[str]:
        return self.tree.commands

    # inherit
    def call(self, command, args, **kwargs):
        return self.tree.call(command, args, **kwargs)

    def step(self, user_said: str = None):
        """单步执行"""

        input_str = self.human_input(user_said)
        return self.invoke(input_str)

    def auto(self, ask: str = None, streaming = True):
        """全自动运行"""

        # 最多允许步数的限制
        counter = 0
        max_steps = 10
        user_said = ask

        while(counter < max_steps):
            counter += 1
            # 获取用户指令
            user_said = self.human_input(user_said)
            result = self.invoke(input_str)

            # 流式返回
            if streaming:
                yield result['reply']

            # 日志输出
            print(result['reply'])

            user_said = None

    def repl(self, ask: str = None):
        """每一步都询问"""

        # 最多允许步数的限制
        counter = 0
        command = None
        prompt = None
        max_steps = 10
        user_said = ask

        while(counter < max_steps):
            counter += 1

            # 获取用户指令
            user_said = self.human_input(user_said)
            result = self.invoke(input_str)

            # 日志输出
            print(result['reply'])

            user_said = None
