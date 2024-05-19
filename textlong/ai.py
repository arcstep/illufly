from typing import Any, Dict, Iterator, List, Optional, Union, Tuple
from langchain_core.runnables import Runnable
from langchain_core.output_parsers import JsonOutputParser
from langchain.schema.output_parser import StrOutputParser
from langchain.memory.chat_memory import BaseChatMemory
from langchain.memory import ConversationBufferWindowMemory
from .prompts import create_writing_help_prompt
import os

class BaseAI():
    """
    向AI提问。
    """
    
    def __init__(self, llm: Runnable=None, memory: BaseChatMemory=None):
        if llm is None:
            if os.environ.get("ZHIPUAI_API_KEY"):
                from langchain_zhipu import ChatZhipuAI
                self.llm = ChatZhipuAI()
            elif os.environ.get("OPENAI_API_KEY"):
                from langchain_openai import ChatOpenAI
                self.llm = ChatOpenAI(model_name="gpt-4-turbo")
            else:
                raise BaseException("您必须指定一个LLM，或者配置正确的环境变量：ZHIPUAI_API_KEY！")
        else:
            self.llm = llm

        self.memory = memory or ConversationBufferWindowMemory(k=10, return_messages=True)

        self.retry_max: int = 5

    def ask_ai(self, task, prompt=None, return_json: bool=False):
        """AI推理"""

        prompt = prompt or create_writing_help_prompt()
        chain = prompt | self.llm | StrOutputParser()

        counter = 0
        while(counter < self.retry_max):
            counter += 1
            # try:
            text = ""
            resp = chain.stream({"task": task, "history": self.memory.buffer})
            for chunk in resp:
                print(chunk, end="", flush=True)
                text += chunk
            print()

            # 存储到记忆管理中
            self.memory.chat_memory.add_user_message(task)
            self.memory.chat_memory.add_ai_message(text)

            if return_json:
                json = JsonOutputParser().invoke(input=text)
                if json:
                    return json
                else:
                    raise BaseException("JSON为空")
            else:
                return text
            # except Exception as e:
            #     print(f"推理错误: ", e)

        raise Exception(f"AI返回结果无法正确解析，已经超过 {self.retry_max} 次，可能需要调整提示语模板！！")
