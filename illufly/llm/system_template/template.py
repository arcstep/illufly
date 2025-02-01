from typing import Dict, Any, Set
from datetime import datetime

import chevron
import re
import logging
from chevron import tokenizer

logger = logging.getLogger(__name__)

from .hub import load_resource_template, load_prompt_template, clone_prompt_template

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
                logger.debug(f"加载模板: {template_id} 从 {template_folder}")
                self.text = load_prompt_template(template_id, template_folder)
            elif template_id:
                logger.debug(f"加载模板: {template_id} 从包内资源")
                self.text = load_resource_template(template_id)
            else:
                raise ValueError('template_id or template_folder is required')
        elif text:
            self.text = text
        else:
            raise ValueError('text or template_id cannot be empty')

        # 添加模板元数据
        self.metadata = {
            'created_at': str(datetime.now()),
            'source': template_id if template_id else 'TEXT',
            'variables': self.variables
        }

    @property
    def variables(self) -> Set[str]:
        """提取模板中的变量名，不包括控制标记"""
        variables = set()
        for token in tokenizer.tokenize(self.text):
            token_type, token_value = token
            # 只提取变量类型的token，忽略section和partial
            if token_type == 'variable':
                # 对于数组中的当前元素引用 {{.}}，不作为必需变量
                if token_value != '.':
                    variables.add(token_value)
        return variables

    def format(self, variables: Dict[str, Any] = {}) -> str:
        """
        格式化模板
        支持条件渲染和默认值语法
        """
        return chevron.render(self.text, variables)

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
