from typing import Any, Dict, Iterator, List, Optional, Union, Tuple
from langchain.pydantic_v1 import BaseModel, Field, root_validator

class BaseHumanInput(BaseModel):
    """
    基于命令行的用户输入，可作为API交互等高级设计的基本框架。
    """
    
    # 可用的参数
    # - askme
    # - all
    auto_mode: str = "askme"

    # 最多重新输入次数
    max_input_count = 30

    def ask(self, user_said: str = None) -> tuple:
        """捕获用户输入"""
        
        counter = 0
        while(counter < max_input_count):
            counter += 1

            if user_said == None:
                # 自动回复 ok 指令
                if self.auto_mode == "all":
                    user_said = "ok"
                else:
                    user_said = get_input()

            # 使用正则表达式解析命令
            match_with_scope = re.match(r'^\s*<([\w-]+)#([\w-]+)>\s*([\w-]+)(.*)$', user_said)
            match_no_scope = re.match(r'^\s*<([\w-]+)>\s*([\w-]+)(.*)$', user_said)
            match_only_command = re.match(r'^([\w-]+)\s+(.*)$', user_said)

            # 提取值
            if match_with_scope:
                id, _scope, command, prompt = match_with_scope.groups()
            elif match_no_scope:
                id, command, prompt = match_no_scope.groups()
            else:
                id = None
                command, prompt = match_only_command.groups()

            # 提取参数值
            prompt = prompt.strip()  # 去除参数前后的空格
            
            # 全部转化为小写
            command = command.lower().strip()
            
            return id, command, prompt
    
    def reply(self, prompt):
        """反馈给用户"""
        print(prompt)
