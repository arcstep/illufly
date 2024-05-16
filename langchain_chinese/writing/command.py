from typing import Any, Dict, Iterator, List, Optional, Union
import re

class BaseCommand():
    """
    继承BaseCommand就可以方便实现指令调度。

    如果命令存在于多个对象中，可能需要实现简单的指令路由，即：
      按照优先顺序检查各个对象中包含的commands，来决定由哪个对象执行指令。
    """

    def commands(self) -> List[str]:
        """
        列举有哪些可用的指令。
        """
        raise NotImplementedError("子类必须实现这个方法")
    
    def default_command(self) -> str:
        return None

    def invoke(self, user_said: str) -> Any:
        """
        从用户输入中解析指令后，直接执行。
        通常，你应该通过重载call函数来定义执行逻辑，再通过invoke函数调用。
        """
        resp = self.parser(user_said)

        if resp and resp['command'] in self.commands():
            resp['reply'] = self.call(**resp)

        return resp

    def call(self, **kwargs):
        """
        执行指令。
        """
        raise NotImplementedError("子类必须实现这个方法")

    def parser(self, user_said: str) -> tuple:
        """
        指令解析器，可以解析用户输入为指令。
        重载该函数可以重新定义你的指令结构解析或输出。

        默认的合法指令格式为: 
            - command args
            - command
            - args
        参数说明:
            - command 命令名称
            - args 命令参数或发送给AI的提示语

        例如: '<0.1> ask 请帮我重新生成'就是向id为'0.1'的内容对象发送AI指令
        """
        if user_said is None:
            return {"id": None, "command": None, "args": None}

        pattern = r'^\s*(' + '|'.join(self.__class__.commands()) + r')?\s*(.*)$'
        match = re.match(pattern, user_said, re.IGNORECASE)

        if match:
            command, args = match.groups()
        command = self.default_command() if command == None else command

        return {"command": command, "args": args}
