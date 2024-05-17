from typing import Any, Dict, Iterator, List, Optional, Union, Tuple
from .tree import ContentTree
from .command import BaseCommand

class WritingTask(BaseCommand):
    """
    长文写作任务。
    """

    def __init__(self):
        self.human_input = lambda x=None : x if x != None else input("\n👤: ")
        self.tree = ContentTree()

    # inherit
    @property
    def default_command(self) -> str:
        return self.tree.default_command

    # inherit
    @property
    def commands(self) -> List[str]:
        return ["quit"] + self.tree.commands

    # inherit
    def call(self, command, args, **kwargs):
        if command == "quit":
            return "<QUIT>"
        else:
            return self.tree.call(command, args, **kwargs)

    def auto_write(self, user_said: str):
        """全自动运行"""

        counter = 0
        max_steps = 1e3

        self.invoke(user_said)
        self.invoke("ok")

        while(counter < max_steps):
            counter += 1

            resp = self.invoke("todo")
            if resp['reply']:
                self.invoke(f"move {resp['reply']}")
                if self.tree.todo_node.state == "init":
                    self.invoke("ok")
                if self.tree.todo_node.state == "todo":
                    self.invoke("task 请继续")
                    self.invoke("ok")
            else:
                print("END")
                break

    def repl_write(self, user_said: str = None):
        """每一步都询问"""

        counter = 0
        max_steps = 1e3

        resp = self.invoke(user_said)
        print(resp)

        while(counter < max_steps):
            counter += 1

            if self.tree.todo_node.is_complete:
                resp = self.invoke("todo")
                if resp['reply']:
                    self.invoke(f"move {resp['reply']}")

                if self.tree.todo_node.state == "init":
                    self.invoke("ok")

                if not self.tree.todo_node.is_draft:
                    self.invoke("task 请继续")
            
            n = self.tree.todo_node
            print(f'<{n.id} #{n.state}> {n.title}')
            print(self.commands)

            user_said = self.human_input()
            resp = self.invoke(user_said)
            print(resp)
            if not resp or resp['reply'] == '<QUIT>':
                print("QUIT")
                break
