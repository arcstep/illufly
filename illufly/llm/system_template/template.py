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
            # 只提取变量类型的token
            if token_type == 'variable':
                variables.add(token_value)
        return variables

    def format(self, variables: Dict[str, Any] = {}) -> str:
        """
        格式化模板
        支持条件渲染和默认值语法
        """
        # 提取所有必需的变量（不包括带有默认值的变量）
        required_vars = set()
        for var in self.variables:
            # 检查变量是否有默认值处理
            has_default = f"{{^{var}}}" in self.text or f"{{#{var}}}" in self.text
            if not has_default:
                required_vars.add(var)

        # 检查必需变量是否存在
        provided_vars = set()
        for key in variables.keys():
            # 处理嵌套结构
            parts = key.split('.')
            provided_vars.add(key)
            for i in range(len(parts)):
                provided_vars.add('.'.join(parts[:i+1]))

        missing_vars = required_vars - provided_vars
        if missing_vars:
            raise ValueError(f"缺少必要的变量: {missing_vars}")

        # 预处理变量，确保空字典被视为有效值
        processed_vars = {}
        for key, value in variables.items():
            if isinstance(value, dict):
                # 空字典也被视为真值
                processed_vars[key] = value if value else {'_empty': True}
            else:
                processed_vars[key] = value

        return chevron.render(self.text, processed_vars)

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

