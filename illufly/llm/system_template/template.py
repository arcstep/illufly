from typing import Dict, Any
from chevron.renderer import render as mustache_render
from datetime import datetime

import logging
logger = logging.getLogger(__name__)

from .hub import load_resource_template, load_prompt_template, get_template_variables, clone_prompt_template

class SystemTemplate():
    """
    系统模板可以作为消息生成消息列表。
    """
    def __init__(
        self,
        template_id: str = None,
        template_folder: str = None,
        text: str = None,
        **kwargs
    ):
        if template_id:
            if template_id and template_folder:
                logger.info(f"加载模板: {template_id} 从 {template_folder}")
                self.text = load_prompt_template(template_id, template_folder)
            elif template_id:
                logger.info(f"加载模板: {template_id} 从包内资源")
                self.text = load_resource_template(template_id)
            else:
                raise ValueError('template_id or template_folder is required')
        elif text:
            self.text = text
        else:
            raise ValueError('text or template_id cannot be empty')
        
        # 添加模板元数据
        self.metadata = {
            'created_at': datetime.now(),
            'source': template_id if template_id else 'custom',
            'variables': self.variables
        }

    def format(self, binding: Dict[str, Any] = None, strict: bool = False):
        """
        添加strict模式，严格检查变量
        """
        if strict:
            missing_vars = set(self.variables) - set(binding.keys())
            if missing_vars:
                raise ValueError(f"缺少必要的模板变量: {missing_vars}")
        
        return mustache_render(template=self.text, data=binding)

    @property
    def variables(self):
        return get_template_variables(self.text)

    def validate(self, data: Dict[str, Any]) -> bool:
        """
        添加模板验证功能
        """
        required_vars = self.variables
        return all(var in data for var in required_vars)

    def clone_to(self, target_path: str) -> str:
        """
        添加模板克隆功能
        """
        if not hasattr(self, 'template_id'):
            raise ValueError("只有从template_id加载的模板才能克隆")
        return clone_prompt_template(self.template_id, target_path)

