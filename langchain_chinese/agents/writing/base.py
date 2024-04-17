from typing import Dict, List, Callable, Any, Optional, Type, Union
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough, Runnable, RunnableAssign
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import BaseMessage
from langchain_core.callbacks import BaseCallbackHandler
from langchain.pydantic_v1 import BaseModel, Field, root_validator

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

CONFIG_FILE = "config.yml"

class BaseProject(BaseModel):
    """
    用于写作复杂文案的智能体。
    为了写作投标书、方案书等工作文档而准备的一系列工具。

    典型的子类包括：
        BookWriting - 写书，包含多个文件
        Article - 写文章
        Reading - 读取资料
    """

    config_path: str = None
    """
    配置文件路径。
    如果未指定，就从当前目录向上层寻找，直到找到配置文件所在的位置；
    如果仍然找不到，就使用当前目录生成配置文件。
    
    从效率和可控性角度考虑，应当在项目初始化时确保这一变量存在。
    """

    project_folder: str = None
    """
    文档根目录。
    如果未明确指定，从当前目录向上层寻找，直到找到配置文件所在的位置。
    """
    
    @root_validator()
    def validate_base_environment(cls, values: Dict) -> Dict:
        if values["config_path"] is None:
            # 从当前目录开始向上查找配置文件
            current_dir = os.getcwd()
            while current_dir != os.path.dirname(current_dir):  # 当前目录不是根目录
                if os.path.exists(os.path.join(current_dir, CONFIG_FILE)):
                    values["config_path"] = os.path.join(current_dir, CONFIG_FILE)
                    break
                else:
                    current_dir = os.path.dirname(current_dir)
            else:
                # 如果在所有上级目录中都找不到配置文件，就在当前目录生成配置文件
                values["config_path"] = os.path.join(os.getcwd(), CONFIG_FILE)
        else:
            # 如果 config_path 是目录，就增加 CONFIG_FILE 的路径
            if os.path.isdir(values["config_path"]):
                values["config_path"] = os.path.join(values["config_path"], CONFIG_FILE)
            # 如果 config_path 是相对路径就扩展为绝对路径
            # 否则直接使用绝对路径
            values["config_path"] = os.path.abspath(values["config_path"])

        if values["project_folder"] is None:
            # 如果未明确指定 project_folder，就设为配置文件所在的目录
            values["project_folder"] = os.path.dirname(values["config_path"])

        return values

    @property
    def config(self):
        """
        读取YAML配置
        """
        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)
        return config

class SaveContentCallbackHandler(BaseCallbackHandler):
    def __init__(self, output_path:str):
        self.output_path = output_path
    
    def on_llm_end(self, response, **kwargs):
        print("-"*20, "OUTPUT_PATH:", self.output_path, "-"*20)
        gen = response.generations
        print(gen[0][0].text)
        print("-"*20)

class BaseWritingChain(BaseProject):
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
        return SaveContentCallbackHandler(output_path=self.output_path())

    def output_path(self):
        """
        结合当前文件夹位置和 output_name 文件名，获得输出文件路径。
        
        output_dir 属性被设置为如下情况都能正确组需要的路径：
        - 未设置，即为默认的None
        - 设置为相对路径
        - 设置为绝对路径
        """
        if self.output_dir is None or not os.path.isabs(self.output_dir):
            output_dir = os.path.join(os.getcwd(), self.output_dir) if self.output_dir else os.getcwd()
        else:
            output_dir = self.output_dir

        path = os.path.join(output_dir, self.output_filename)
        return os.path.abspath(path)
    
    @root_validator()
    def validate_writing_environment(cls, values: Dict) -> Dict:
        values["output_filename"] = "./index.md" if values["output_filename"] is None else values["output_filename"]
        values["output_dir"] = os.getcwd() if values["output_dir"] is None else values["output_dir"]
        
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