from typing import Dict, Any, Set
from datetime import datetime

import chevron
import re
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

    @property
    def variables(self) -> Set[str]:
        """提取模板中的变量名"""
        pattern = r'\{\{([^}>]+)\}\}'  # 修改正则以排除>号
        matches = re.finditer(pattern, self.text)
        return {match.group(1).strip() for match in matches}

    def format(self, variables: Dict[str, Any]) -> str:
        """格式化模板"""
        # 检查所有必需的变量是否存在
        template_vars = self.variables
        provided_vars = set()
        for key in variables.keys():
            # 处理嵌套结构
            parts = key.split('.')
            provided_vars.add(key)
            for i in range(len(parts)):
                provided_vars.add('.'.join(parts[:i+1]))
        missing_vars = template_vars - provided_vars
        if missing_vars:
            raise ValueError(f"缺少必要的变量: {missing_vars}")
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

