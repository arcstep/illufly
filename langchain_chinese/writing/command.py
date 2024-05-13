from typing import Any, Dict, Iterator, List, Optional, Union

class BaseCommand():
    name: [str] =  Optional(None)
    target: ["TreeContent"] = Optional(None)
    prompt: [str] = Optional(None)
    
    def invoke(self):
        return {"reply": "unkown"}
    
    def help(self):
        pass

    def process_content_command(k, v):
        # 设置内容属性
        if target and v != None:
            target.set_prompt_input(k, v)

        # 打印指定对象的指定属性
        if target:
            print(f'{k:}', target.get_prompt_input(k))
    
    @staticmethod
    def create_command(cls, command_name: str, target: ["TreeContent"] = None, prompt: str = None):
        """构造命令对象"""

        if command_name == "quit":
            return CommandQuit(target, prompt)

        elif command_name == "all":
            return CommandAll(target, prompt)
        elif command_name == "todos":
            return CommandTodos(target, prompt)
        elif command_name == "todo":
            return CommandTodo(target, prompt)

        elif command_name == "ok":
            return CommandOK(target, prompt)

        elif command_name == "children":
            return CommandChildren(target, prompt)
        elif command_name == "title":
            return CommandTitle(target, prompt)
        elif command_name == "words":
            return CommandWords(target, prompt)
        elif command_name == "howto":
            return CommandHowto(target, prompt)
        elif command_name == "summarise":
            return CommandSummarise(target, prompt)
        elif command_name == "text":
            return CommandText(target, prompt)

        elif command_name == "ask":
            return CommandAsk(target, prompt)
        elif command_name == "reply":
            return CommandReply(target, prompt)

        elif command_name == "reload":
            return CommandReload(target, prompt)
        elif command_name == "memory":
            return CommandMemory(target, prompt)
        elif command_name == "store":
            return CommandStore(target, prompt)
        else:
            raise BaseException("Unkown Command Name:", command_name)

class CommandQuit(BaseCommand):
    def __init__(self):
        self.name = "quit"
    
    def invoke(self):
        return {"reply": "end"}

class CommandAll(BaseCommand):
    def __init__(self):
        self.name = "all"
    
    def invoke(self):
        return {"reply": "end"}

class CommandTodos(BaseCommand):
    def __init__(self):
        self.name = "todos"
    
    def invoke(self):
        return {"reply": "end"}

class CommandTodo(BaseCommand):
    def __init__(self):
        self.name = "todo"
    
    def invoke(self):
        return {"reply": "end"}

class CommandOK(BaseCommand):
    def __init__(self):
        self.name = "ok"
    
    def invoke(self):
        return {"reply": "end"}

class CommandChildren(BaseCommand):
    def __init__(self):
        self.name = "children"
    
    def invoke(self):
        self.process_content_command('children', None)
        return {"reply": "success"}

class CommandTitle(BaseCommand):
    def __init__(self):
        self.name = "title"
    
    def invoke(self):
        self.process_content_command('title', self.prompt)
        return {"reply": "success"}

class CommandHowto(BaseCommand):
    def __init__(self):
        self.name = "howto"
    
    def invoke(self):
        self.process_content_command('howto', self.prompt)
        return {"reply": "success"}

class CommandSummarise(BaseCommand):
    def __init__(self):
        self.name = "summarise"
    
        self.process_content_command('summarise', self.prompt)
        return {"reply": "success"}

class CommandWords(BaseCommand):
    def __init__(self):
        self.name = "words"
    
    def invoke(self):
        prompt = self.prompt
        if prompt and prompt.isdigit():
            prompt = int(prompt)
        self.process_content_command('words_advice', prompt)
        return {"reply": "success"}

class CommandText(BaseCommand):
    def __init__(self):
        self.name = "text"
    
    def invoke(self):
        self.process_content_command('text', self.prompt)
        return {"reply": "success"}

class CommandAsk(BaseCommand):
    def __init__(self):
        self.name = "ask"
    
    def invoke(self):
        return {"reply": "end"}

class CommandReply(BaseCommand):
    def __init__(self):
        self.name = "reply"
    
    def invoke(self):
        return {"reply": "end"}

class CommandReload(BaseCommand):
    def __init__(self):
        self.name = "reload"
    
    def invoke(self):
        return {"reply": "end"}

class CommandMemory(BaseCommand):
    def __init__(self):
        self.name = "memory"
    
    def invoke(self):
        return {"reply": "end"}

class CommandStore(BaseCommand):
    def __init__(self):
        self.name = "store"
    
    def invoke(self):
        return {"reply": "end"}

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