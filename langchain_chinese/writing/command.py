from typing import Any, Dict, Iterator, List, Optional, Union

class BaseCommand():
    """
    标准化命令格式为： <id#scope> command prompt
    参数说明：
        - id 内容ID, "0", "0.1.2"
        - scope 描述视角的字符串，可使用下列值：
        - command 命令名称
        - prompt 命令参数或发送给AI的提示语
    
    与ID组合起来即为内容节点的session_id
    例如： `<0.1#create> ask 请帮我重新生成`就是向id为‘0.1’的内容对象发送AI指令

    """
    def __init__(self, bound: [Any] = None, prompt: [str] = None):
        self.bound = bound if bound == None else self.bound
        self.prompt = prompt if prompt == None else self.prompt

    def invoke(self):
        return {"reply": "unkown"}
    
    def help(self):
        pass

    def process_content_command(k, v):
        # 设置内容属性
        if self.bound and v != None:
            self.bound.set_prompt_input(k, v)

        # 打印指定对象的指定属性
        if bound:
            print(f'{k:}', self.bound.get_prompt_input(k))
    
class CommandQuit(BaseCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "quit"
    
    def invoke(self):
        return {"reply": "end"}

class CommandAll(BaseCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "all"
    
    def invoke(self):
        return {"reply": "end"}

class CommandTodos(BaseCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "todos"
    
    def invoke(self):
        return {"reply": "end"}

class CommandTodo(BaseCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "todo"
    
    def invoke(self):
        return {"reply": "end"}

class CommandOK(BaseCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "ok"
    
    def invoke(self):
        return {"reply": "end"}

class CommandChildren(BaseCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "children"
    
    def invoke(self):
        self.process_content_command('children', None)
        return {"reply": "success"}

class CommandTitle(BaseCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "title"
    
    def invoke(self):
        self.process_content_command('title', self.prompt)
        return {"reply": "success"}

class CommandHowto(BaseCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "howto"
    
    def invoke(self):
        self.process_content_command('howto', self.prompt)
        return {"reply": "success"}

class CommandSummarise(BaseCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "summarise"
    
        self.process_content_command('summarise', self.prompt)
        return {"reply": "success"}

class CommandWords(BaseCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "words"
    
    def invoke(self):
        prompt = self.prompt
        if prompt and prompt.isdigit():
            prompt = int(prompt)
        self.process_content_command('words_advice', prompt)
        return {"reply": "success"}

class CommandText(BaseCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "text"
    
    def invoke(self):
        self.process_content_command('text', self.prompt)
        return {"reply": "success"}

class CommandAsk(BaseCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "ask"
    
    def invoke(self):
        return {"reply": "end"}

class CommandReply(BaseCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "reply"
    
    def invoke(self):
        return {"reply": "end"}

class CommandReload(BaseCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "reload"
    
    def invoke(self):
        return {"reply": "end"}

class CommandMemory(BaseCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "memory"
    
    def invoke(self):
        return {"reply": "end"}

class CommandStore(BaseCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "store"
    
    def invoke(self):
        return {"reply": "end"}

def create_command(bound: [Any] = None, command_name: str = "Unknown", prompt: str = None):
    """构造命令对象"""

    if command_name == "quit":
        return CommandQuit(bound, prompt)

    elif command_name == "all":
        return CommandAll(bound, prompt)
    elif command_name == "todos":
        return CommandTodos(bound, prompt)
    elif command_name == "todo":
        return CommandTodo(bound, prompt)

    elif command_name == "ok":
        return CommandOK(bound, prompt)

    elif command_name == "children":
        return CommandChildren(bound, prompt)
    elif command_name == "title":
        return CommandTitle(bound, prompt)
    elif command_name == "words":
        return CommandWords(bound, prompt)
    elif command_name == "howto":
        return CommandHowto(bound, prompt)
    elif command_name == "summarise":
        return CommandSummarise(bound, prompt)
    elif command_name == "text":
        return CommandText(bound, prompt)

    elif command_name == "ask":
        return CommandAsk(bound, prompt)
    elif command_name == "reply":
        return CommandReply(bound, prompt)

    elif command_name == "reload":
        return CommandReload(bound, prompt)
    elif command_name == "memory":
        return CommandMemory(bound, prompt)
    elif command_name == "store":
        return CommandStore(bound, prompt)
    else:
        raise BaseException("Unkown Command Name:", command_name)

__all__ = [
    "BaseCommand",
    
    "CommandQuit",

    "CommandAll",
    "CommandTodos",
    "CommandTodo",

    "CommandOK",

    "CommandChildren",
    "CommandTitle",
    "CommandWords",
    "CommandHowto",
    "CommandSummarise",
    "CommandText",

    "CommandAsk",
    "CommandReply",
    "CommandReload",
    "CommandMemory",
    "CommandStore",
]