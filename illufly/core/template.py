from typing import Dict, Any

from ..utils import compress_text
from ..hub import load_resource_template, load_template, get_template_variables

from chevron.renderer import render as mustache_render
from chevron.tokenizer import tokenize as mustache_tokenize

class Template:
    """
    提示语模板可以作为消息生成消息列表。
    结合工作台映射，可以动态填充提示语模板。
    """
    def __init__(self, template_id: str=None, template_text: str=None, input_mapping: Dict[str, Any]=None):
        if template_id:
            self.template_text = load_template(template_id)
        elif template_text:
            self.template_text = template_text
        else:
            raise ValueError('template is not set')

        self.input_variables = get_template_variables(self.template_text)
        self.input_mapping = self._get_desk_map(self.input_variables, input_mapping or {})
        self.using_vars_list = self._get_using_vars(self.input_variables, self.input_mapping or {})

    def _get_desk_map(self, input_variables, input_mapping):
        return {**input_mapping, **{k: k for k in input_variables if k not in input_mapping}}

    def _get_using_vars(self, input_variables, input_mapping):
        mapping = [v for k, v in input_mapping.items() if k in input_variables]
        not_mapping = [k for k in input_variables if k not in input_mapping]
        return mapping + not_mapping

    def __str__(self):
        return compress_text(mustache_render(template=self.template_text))
    
    def __repr__(self):
        return f"<Template input_variables={self.input_variables} template_text='{compress_text(self.template_text)}'>"

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

        _input_vars = input_vars or {}
        if _input_vars:
            for k, v in self.input_mapping.items():
                if '.' in v:
                    keys = v.split('.')
                    _input_vars[k] = get_nested_value(_input_vars, keys)
                else:
                    _input_vars[k] = _input_vars.get(v, '')

        return mustache_render(template=self.template_text, data=_input_vars)

