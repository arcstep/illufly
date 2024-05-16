from typing import Any, Dict, Iterator, List, Optional, Union, Tuple
from langchain_core.runnables import Runnable
from langchain.memory import ConversationBufferMemory, ConversationBufferWindowMemory
from ..memory.history import LocalFileMessageHistory, create_session_id
from ..memory.memory_manager import MemoryManager
from ..memory.base import WithMemoryBinding
from .prompts.task_prompt import *
import os

class BaseAI():
    """
    向AI提问。
    """
    
    def __init__(self, llm: Runnable = None, memory: Optional[MemoryManager] = None):
        if llm == None:
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

        self.memory = memory
        self.retry_max: int = 5
    
    def prompt_default(self):
        default_prompt = DEFAULT_PROMPT

        prompt = ChatPromptTemplate.from_messages([
            ("system", default_prompt),
            ("ai", "好的。"),
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
            ("ai", "好的，我会尽最大努力。"),
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
        content_type: str = "paragraph",
        words_per_step: int = 500,
        words_advice: int = 500,
        howto: str = None,
        outline_exist: List[Any] = None,
    ):
        main_prompt = MAIN_PROMPT
        auto_prompt = _AUTO_OUTLINE_OR_PARAGRAPH_PROMPT
        if content_type == "outline":
            task_prompt   = _OUTLINE_TASK
            output_format = _OUTLINE_FORMAT
        else:
            task_prompt   = _PARAGRAPH_TASK
            output_format = _PARAGRAPH_FORMAT

        prompt = ChatPromptTemplate.from_messages([
            ("system", main_prompt),
            ("ai", "你对我的写作有什么要求？"),
            ("human", auto_prompt),
            ("ai", "好的，我会尽最大努力。"),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{{task}}")
        ], template_format="jinja2").partial(
            # 字数限制
            words_limit=self.words_per_step,
            words_advice=self.todo_content.words_advice,
            # 写作提纲
            title=self.todo_content.title,
            outline_exist=outline_exist,
            # 任务指南
            task_instruction=task_prompt,
            howto=self.todo_content.howto,
            # 输出格式要求
            output_format=output_format,
            # JSON严格控制
            json_instruction=json_instruction,
        )

        return prompt

    def template_modi(self):
        return None
    
    def get_chain(self, prompt = None):
        # 构造链
        chain = (prompt or self.prompt_default()) | self.llm
        # print(prompt.format(task="<<DEMO_TASK>>", history=[]))

        # 记忆绑定管理
        withMemoryChain = WithMemoryBinding(
            chain,
            memory,
            input_messages_key="task",
            history_messages_key="history",
        )

        return withMemoryChain

    def ask_ai(self, chain: Runnable, session_id = "default", return_json = True, **kwargs):
        """AI推理"""

        counter = 0
        while(counter < self.retry_max):
            counter += 1
            try:
                config = {"configurable": {"session_id": session_id}}
                kwargs["config"] = config
                text = ""
                if self.streaming:
                    for resp in chain.stream(**kwargs):
                        print(resp.content, end="", flush=True)
                        text += resp.content
                    print()
                else:
                    resp = chain.invoke(**kwargs)
                    print("resp:", resp.content)
                    text = resp.content

                if return_json:
                    return text
                else:
                    json = JsonOutputParser().invoke(input=text)
                    if json:
                        return json
                    else:
                        raise BaseException("JSON为空")
            except Exception as e:
                print(f"推理错误: {e}")

        raise Exception(f"AI返回结果无法正确解析，已经超过 {self.retry_max} 次，可能需要调整提示语模板！！")
