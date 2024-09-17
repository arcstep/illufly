from typing import Dict, Any
from langchain.prompts import PromptTemplate

from ..hub import load_resource_template, load_template
from ..utils import compress_text

class Template:
    """
    提示语模板可以作为消息生成消息列表。

    结合工作台映射，可以动态填充提示语模板。
    """
    def __init__(self, template_id: str=None, template_text: str=None, input_mapping: Dict[str, Any]=None):
        self.template_id = template_id
        self.template_text = template_text

        self.template = self._get_template(self.template_id, self.template_text)
        self.input_mapping = self._get_desk_map(self.template, input_mapping or {})
        self.using_vars_list = self._get_using_vars(self.template, self.input_mapping or {})

    def _get_template(self, template_id, template_text):
        if template_id:
            mu = load_template(template_id)
        elif template_text:
            mu = PromptTemplate.from_template(template_text, template_format='mustache')
        else:
            raise ValueError('template is not set')
        return mu

    def _get_desk_map(self, template, input_mapping):
        return {**input_mapping, **{k: k for k in template.input_variables if k not in input_mapping}}
    
    def _get_using_vars(self, template,input_mapping):
        mapping = [v for k, v in input_mapping.items() if k in template.input_variables]
        not_mapping = [k for k in template.input_variables if k not in input_mapping]
        return mapping + not_mapping

    def __str__(self):
        return compress_text(self.template.format())
    
    def __repr__(self):
        if self.template_id:
            return f"<Template template_id='{self.template_id}'>"
        else:
            return f"<Template template_text='{compress_text(self.template_text)}'>"

    def clone(self):
        return self.__class__(
            template_id=self.template_id,
            template_text=self.template_text,
            input_mapping=self.input_mapping
        )

    def format(self, input_vars: Dict[str, Any]=None):
        def get_nested_value(d, keys):
            new_desk = {}
            for key in keys:
                new_desk = (new_desk or d).get(key, {})
                if not new_desk:
                    break
            return new_desk
        
        input_vars = {}
        if input_vars:
            for k, v in self.input_mapping.items():
                if '.' in v:
                    keys = v.split('.')
                    input_vars[k] = get_nested_value(input_vars, keys)
                else:
                    input_vars[k] = input_vars.get(v, '')

        return self.template.format(**input_vars)

