from typing import Any, Dict, Iterator, List, Optional, Union, Tuple
from langchain_core.runnables import Runnable
from langchain_core.output_parsers import JsonOutputParser
from langchain.schema.output_parser import StrOutputParser
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferWindowMemory
from .prompts.task_prompt import *
import os

class BaseAI():
    """
    向AI提问。
    """
    
    def __init__(self, llm: Runnable=None):
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

        self.memory = ConversationBufferWindowMemory(k=20, return_messages=True)

        self.retry_max: int = 5
    
    def prompt_default(self):
        default_prompt = DEFAULT_PROMPT

        prompt = ChatPromptTemplate.from_messages([
            ("system", default_prompt),
            ("ai", "OK"),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{{task}}"),
        ], template_format="jinja2")

        return prompt

    def prompt_init(self):
        main_prompt = MAIN_PROMPT
        task_prompt   = _ROOT_TASK
        output_format = _ROOT_FORMAT
        json_instruction = _JSON_INSTRUCTION 

        prompt = ChatPromptTemplate.from_messages([
            ("system", main_prompt),
            ("ai", "OK"),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{{task}}"),
        ], template_format="jinja2").partial(
            # 任务指南
            task_instruction=task_prompt,
            # 输出格式要求
            output_format=output_format,
            # JSON严格控制
            json_instruction=json_instruction,
        )

        return prompt

    def prompt_todo(
        self,
        title: str,
        content_type: str="paragraph",
        words_limit: int=500,
        words_advice: int=500,
        howto: str=None,
        outline_exist: List[Any]=None,
    ):
        main_prompt = MAIN_PROMPT
        auto_prompt = _AUTO_OUTLINE_OR_PARAGRAPH_PROMPT
        json_instruction = _JSON_INSTRUCTION 

        if content_type == "outline":
            task_prompt   = _OUTLINE_TASK
            output_format = _OUTLINE_FORMAT
        else:
            task_prompt   = _PARAGRAPH_TASK
            output_format = _PARAGRAPH_FORMAT

        prompt = ChatPromptTemplate.from_messages([
            ("system", main_prompt),
            ("ai", "有什么具体要求？"),
            ("human", auto_prompt),
            ("ai", "OK"),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{{task}}")
        ], template_format="jinja2").partial(
            # 字数限制
            words_limit=words_limit,
            words_advice=words_advice,
            # 写作要求
            title=title,
            outline_exist=outline_exist,
            task_instruction=task_prompt,
            howto=howto,
            # 输出格式要求
            output_format=output_format,
            # JSON严格控制
            json_instruction=json_instruction,
        )

        return prompt

    def template_modi(self):
        return None
    
    def get_chain(self, prompt=None):
        # 构造链
        if prompt == None:
            chain = self.prompt_default() | self.llm | StrOutputParser()
        else:
            chain = prompt | self.llm | StrOutputParser()

        return chain

    def ask_ai(self, task, chain: Runnable=None, return_json=True):
        """AI推理"""

        chain = chain or self.get_chain()

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
