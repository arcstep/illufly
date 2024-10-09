from typing import Dict, Any

from ...utils import minify_text
from ...hub import load_resource_template, load_template, get_template_variables
from ...io import EventBlock
from .base import Runnable
from chevron.renderer import render as mustache_render

class Template(Runnable):
    """
    提示语模板可以作为消息生成消息列表。
    结合绑定映射，可以动态填充提示语模板。
    """
    def __init__(self, template_id: str=None, text: str=None, binding_map: Dict=None, **kwargs):
        super().__init__(**kwargs)

        if template_id:
            self.text = load_template(template_id)
        elif text:
            self.text = text
        else:
            raise ValueError('text or template_id cannot be empty')

        self.bind_provider(binding_map=binding_map)
        self.template_vars = get_template_variables(self.text)

    def __str__(self):
        return self.format()

    def __repr__(self):
        return f"<Template consumer_dict={self.template_vars} text='{minify_text(self.text)}'>"

    def call(self, *args, **kwargs):
        self._last_output = self.format(*args, **kwargs)
        yield EventBlock("info", self._last_output)

    def format(self, binding_map: Dict[str, Any]=None):
        if binding_map:
            self.bind_provider(binding_map=binding_map)
        _binding = self.consumer_dict
        return mustache_render(template=self.text, data=_binding)

