from typing import Dict, Any
from langchain.prompts import PromptTemplate

from .base import load_resource_template, load_template

class Template:
    def __init__(self, template_id: str=None, template_text: str=None, desk_map: Dict[str, Any]=None, desk: Dict[str, Any]=None):
        self.template_id = template_id
        self.template_text = template_text
        self.desk_map = desk_map or {}
        self.desk = desk or {}

    def __str__(self):
        return self.template

    @property
    def template(self):
        if self.template_id:
            mu = load_template(self.template_id)
        elif self.template_text:
            mu = PromptTemplate.from_template(self.template_text, template_format='mustache')
        else:
            raise ValueError('template is not set')
        
        return mu

    def get_prompt(self, **kwargs):
        def get_nested_value(d, keys):
            for key in keys:
                d = d.get(key, {})
            return d

        # 获取需要的键
        required_keys = self.template.input_variables

        # 应用desk_map映射规则并保留必要的键值
        # 保留没有映射规则且在required_keys中的部分
        mapped_desk = {}
        for k, v in self.desk.items():
            if k not in self.desk_map and k in required_keys:
                mapped_desk[k] = v

        for k, v in self.desk_map.items():
            if k in required_keys:
                keys = v.split('.')
                mapped_desk[k] = get_nested_value(self.desk, keys)

        filtered_kwargs = {k: v for k, v in {**kwargs, **mapped_desk}.items()}

        return self.template.format(**{**mapped_desk, **kwargs})
