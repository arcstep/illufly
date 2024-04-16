from langchain.pydantic_v1 import BaseModel, Field, root_validator
from typing import (
    Dict
)
import os
import yaml

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


class BaseWriting(BaseProject):
    """
    简单的写作能力。
    """
    
    output_name: str = None
    """
    文档输出路径，可使用相对路径。
    如果未明确指定，应当使用 "./index.md"
    """

    @property
    def output_path(self):
        """
        结合当前文件夹位置和output_name文件名，获得输出文件路径
        """
        return os.path.join(os.getcwd(), self.output_name)

    @root_validator()
    def validate_writing_environment(cls, values: Dict) -> Dict:
        if values["output_name"] is None:
            # 如果未明确指定 project_folder，就设为配置文件所在的目录
            values["output_name"] = "./index.md"

        return values

