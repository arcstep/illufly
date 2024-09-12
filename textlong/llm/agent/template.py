from typing import Dict

from .base import Runnable
from ...io import TextBlock
from ...utils import compress_text
from ...hub import load_chat_template

class Template(Runnable):
    """
    """
    def __init__(self, template: str=None, role: str=None):
        super().__init__()

        self.template = template or "IDEA"
        self.role = role or "system"

    def call(self, values: Dict[str, str], prompt: str=None, *args, **kwargs):
        user_prompt = prompt or "请开始"
        system_template = load_chat_template(self.template)
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
