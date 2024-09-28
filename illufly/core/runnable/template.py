from typing import Dict, Any

from ...utils import minify_text
from ...hub import load_resource_template, load_template, get_template_variables
from ...io import TextBlock
from .base import Runnable

from chevron.renderer import render as mustache_render

class Template(Runnable):
    """
    提示语模板可以作为消息生成消息列表。
    结合工作台映射，可以动态填充提示语模板。
    """
    def __init__(self, template_id: str=None, template_text: str=None, **kwargs):
        super().__init__(**kwargs)
        if template_id:
            self.template_text = load_template(template_id)
        elif template_text:
            self.template_text = template_text
        else:
            raise ValueError('template_text or template_id cannot be empty')

        self.template_vars = get_template_variables(self.template_text)

    def __str__(self):
        return self.format()

    def __repr__(self):
        return f"<Template template_vars={self.template_vars} template_text='{minify_text(self.template_text)}'>"


    def call(self, *args, **kwargs):
        self._last_output = self.format(*args, **kwargs)
        yield TextBlock("info", self._last_output)

    def format(self, input_vars: Dict[str, Any]=None):
        _input_vars = {**self.imported_vars, **(input_vars or {})}
        return mustache_render(template=self.template_text, data=_input_vars)

