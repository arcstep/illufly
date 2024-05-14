from typing import Any, Dict, Iterator, List, Optional, Union, Tuple
from langchain.pydantic_v1 import BaseModel, Field, root_validator
from langchain.memory import ConversationBufferMemory, ConversationBufferWindowMemory
from ..memory.history import LocalFileMessageHistory, create_session_id
from ..memory.memory_manager import MemoryManager
from ..memory.base import WithMemoryBinding

class BaseAI(BaseModel):
    """
    向AI提问。
    """
    
    # 可用的参数
    # - askme
    # - all
    auto_mode: str = "askme"

    # 最多重新输入次数
    max_input_count = 30

    def update_chain(self, llm: Runnable = None, memory: Optional[MemoryManager] = None):
        """构造Chain"""
        
        # 获取内容类型
        content_type = self.get_content_type()
        
        # 构造基础示语模板
        json_instruction = _JSON_INSTRUCTION
        
        if content_type == None:
            prompt = ChatPromptTemplate.from_messages([
                ("system", END_PROMPT),
                ("ai", "好的。"),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{{task}}"),
            ], template_format="jinja2")
        elif content_type == "START":
            task_prompt   = _ROOT_TASK
            output_format = _ROOT_FORMAT
            
            prompt = ChatPromptTemplate.from_messages([
                ("system", MAIN_PROMPT),
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
        else:
            # 获取背景信息
            outline_exist = self.root_content.get_outlines()

            if content_type == "outline":
                task_prompt   = _OUTLINE_TASK
                output_format = _OUTLINE_FORMAT
            else:
                task_prompt   = _PARAGRAPH_TASK
                output_format = _PARAGRAPH_FORMAT

            prompt = ChatPromptTemplate.from_messages([
                ("system", MAIN_PROMPT),
                ("ai", "你对我的写作有什么要求？"),
                ("human", _AUTO_OUTLINE_OR_PARAGRAPH_PROMPT),
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

        # 根据环境变量选择默认的LLM
        if llm == None:
            if os.environ.get("ZHIPUAI_API_KEY"):
                from langchain_zhipu import ChatZhipuAI
                llm = ChatZhipuAI()
            elif os.environ.get("OPENAI_API_KEY"):
                from langchain_openai import ChatOpenAI
                llm = ChatOpenAI(model_name="gpt-4-turbo")
            else:
                raise BaseException("您必须指定一个LLM，或者配置正确的环境变量：ZHIPUAI_API_KEY！")

        # 构造链
        chain = prompt | llm
        # print(prompt.format(task="<<DEMO_TASK>>", history=[]))

        # 记忆绑定管理
        withMemoryChain = WithMemoryBinding(
            chain,
            memory,
            input_messages_key="task",
            history_messages_key="history",
        )
        
        return withMemoryChain

    def ask_ai(self, chain: Runnable, task: str):
        """AI推理"""
        
        if len(task) == 0:
            return
        
        # print("ask AI:", task)
        # print(chain.get_prompts())

        json = None
        counter = 0
        while(counter < self.retry_max):
            counter += 1
            try:
                input = {"task": task}
                config = {"configurable": {"session_id": f'{self.focus}'}}
                text = ""
                if self.streaming:
                    for resp in chain.stream(input, config=config):
                        print(resp.content, end="", flush=True)
                        text += resp.content
                    print()
                else:
                    resp = chain.invoke(input, config=config)
                    print("resp:", resp.content)
                    text = resp.content

                if self.focus == "END":
                    return text
                else:
                    json = JsonOutputParser().invoke(input=text)
                    if json:
                        self.ai_reply_json = json
                        return json
                    else:
                        raise BaseException("JSON为空")
            except Exception as e:
                print(f"推理错误: {e}")

        raise Exception(f"AI返回结果无法正确解析，已经超过 {self.retry_max} 次，可能需要调整提示语模板了！！")
