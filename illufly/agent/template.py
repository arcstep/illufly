from typing import Dict

from .base import Runnable
from ..io import TextBlock
from ..utils import compress_text
from ..hub import load_prompt

class Template(Runnable):
    """
    """
    def __init__(self, template_id: str=None, role: str=None, **kwargs):
        super().__init__("TEMPLATE", **kwargs)

        self.template_id = template_id or "IDEA"
        self.role = role or "system"
    
    def clone(self):
        new_obj = super().clone()
        new_obj.template_id = self.template_id
        new_obj.role = self.role
        return new_obj

    def call(self, values: Dict[str, str], prompt: str=None, *args, **kwargs):
        user_prompt = prompt or "请开始"
        system_template = load_prompt(self.template_id)
        template_prompt = system_template.format(**values)
        # 构造提示语
        self.memory.clear()
        if self.role == "system":
            self.memory.extend([
                {
                    'role': "system",
                    'content': template_prompt
                },
                {
                    'role': "user",
                    'content': user_prompt
                }
            ])
        else:
            self.memory.append({
                'role': self.role,
                'content': template_result
            })

        yield TextBlock("info", template_prompt)
