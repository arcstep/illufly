from typing import Dict, List, Callable, Any, Optional, Type, Union
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough, Runnable, RunnableAssign
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import BaseMessage
from langchain_core.callbacks import BaseCallbackHandler
from langchain.pydantic_v1 import BaseModel, Field, root_validator

from dotenv import find_dotenv, load_dotenv
import os
import yaml

from .prompts.main import (
    OPENAI_PROMPT_TEMPLATE, 
    CHAIN_PROMPT_TEMPLATE,
)

def format_docs(docs: List[str]) -> str:
    return "\n\n".join([d.page_content for d in docs])

def convert_message_to_str(message: Union[BaseMessage, str]) -> str:
    if isinstance(message, BaseMessage):
        return message.content
    else:
        return message

class BaseProject(BaseModel):
    """
    用于写作复杂文案的智能体。
    为了写作投标书、方案书等工作文档而准备的一系列工具。
    """

    project_folder: str = Field(
        None,
        description="文档根目录。如果未明确指定，就从环境变量中读取。建议使用 .env 来管理这一配置。"
    )
    
    @root_validator()
    def validate_base_environment(cls, values: Dict) -> Dict:
        project_folder = values.get("project_folder")

        # 如果 project_folder 是 None，尝试从环境变量中获取
        if project_folder is None:
            project_folder = os.getenv("PROJECT_FOLDER")

        # 如果 PROJECT_FOLDER 是相对路径，将其转换为相对于 .env 文件的绝对路径
        if project_folder and not os.path.isabs(project_folder):
            dotenv_path = find_dotenv()
            dotenv_dir = os.path.dirname(dotenv_path)
            project_folder = os.path.join(dotenv_dir, project_folder)

        # 如果 PROJECT_FOLDER 仍然是 None，抛出错误
        if project_folder is None:
            raise ValueError("PROJECT_FOLDER 环境变量未设置")

        values["project_folder"] = project_folder

        return values

class SaveContentCallbackHandler(BaseCallbackHandler):
    def __init__(self, output_path:str):
        self.output_path = output_path
    
    def on_llm_end(self, response, **kwargs):
        print("-"*20, "OUTPUT_PATH:", self.output_path, "-"*20)
        gen = response.generations
        print(gen[0][0].text)
        print("-"*20)

class WritingChain(BaseProject):
    """
    简单的写作能力。
    """
    
    output_filename: str = None
    """
    输出的文档名，默认为 "index.md"。
    """
    
    output_dir: str = None
    """
    文档输出的相对路径，默认是当前文件夹。
    """

    llm: Runnable = None
    """
    具有推理能力的的大模型。
    """

    retriever: Callable = None
    """
    向量查询对象。
    """

    prompt: str = None
    """
    提示语模板。    
    """

    class Config:
        arbitrary_types_allowed = True

    def save_content_handler(self):
        return SaveContentCallbackHandler(output_path=self.get_output_path())

    def get_output_path(self, output_filename: str=None):
        """
        结合 output_dir 和 output_name 文件名，获得输出文件路径。
        """
        filename = output_filename if output_filename else self.output_filename
        path = os.path.join(self.output_dir, filename)
        return os.path.abspath(path)
    
    @root_validator()
    def validate_writing_environment(cls, values: Dict) -> Dict:
        if not values["output_filename"]:
            filename = os.getenv("OUTPUT_FILENAME")
            if not filename:
                values["output_filename"] = filename
            else:
                values["output_filename"] = "001.md"

        if not values["output_dir"]:
            values["output_dir"] = values["project_folder"]
        elif not os.path.isabs(values["output_dir"]):
            values["output_dir"] = os.path.join(values["project_folder"], values["output_dir"])

        if values["llm"] is None:
            raise BaseException("llm MUST NOT None!")

        if values["prompt"] is None:
            values["prompt"] = CHAIN_PROMPT_TEMPLATE

        return values

    def get_chain(self, **kwargs) -> Callable:
        """
        构建写作链。
        
        kwargs - 可以修改提示语模板中的键值，但请不要使用这些键名：'agent_scratchpad', 'chat_history', 'input', 'knowledge'
        """

        params = ({
            key: (kwargs[key] if key in kwargs else "暂无。")
            for key in self.prompt.input_variables
            if key not in ['agent_scratchpad', 'chat_history', 'input', 'knowledge']
        })

        prompt = self.prompt.partial(**params)

        return (
            {
                "knowledge": lambda x: self._query_kg(convert_message_to_str(x)),
                "input": lambda x: convert_message_to_str(x) ,
            }
            | prompt
            | self.llm.with_config(callbacks=[self.save_content_handler()])
        )

    def _query_kg(self, query):
        if self.retriever is not None:
            return (lambda x: query | self.retriever | format_docs)
        else:
            return (lambda x: "暂无。")