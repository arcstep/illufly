"""
    提示语模板采用了`mustache`语法，这是一种逻辑无关的模板语法，包括以下特性：
    1. **变量替换**：使用`{{variable}}`来插入变量的值。
    2. **注释**：使用`{{! comment }}`来添加不会在渲染结果中显示的注释。
    3. **条件判断**：使用`{{#condition}}{{/condition}}`来进行条件判断，如果条件为真，则渲染内部的内容。
    4. **部分模板**：使用`{{> partial}}`来包含另一个模板文件。
    ... 还有其他一些可用的特性
"""

from typing import List, Dict, Any, Union, Set
from importlib.resources import files
from pathlib import Path
from functools import lru_cache

import os
import re
import json
import shutil
import importlib.resources
import logging
from chevron import tokenizer

logger = logging.getLogger(__name__)

# 定义默认模板基础路径
PROMPT_WRITING_BASE = "illufly.prompt.DEFAULT_TEMPLATES"

def find_resource_template(*seg_path):
    """
    过滤出提示语模板所在的目录清单。
    """
    try:
        package_path = ".".join([PROMPT_WRITING_BASE, *seg_path])
        return [p.name for p in importlib.resources.files(package_path).iterdir()]
    except Exception as e:
        raise ValueError(f"无效的模板路径: {'/'.join(seg_path)}")

@lru_cache(maxsize=128)
def load_resource_template(template_id: str) -> str:
    """加载包内提示语模板"""
    parts = template_id.split('/')
    if parts[-1] not in find_resource_template(*parts[:-1]):
        raise ValueError(f"无效的模板ID: {template_id}")
    
    try:
        package_path = ".".join([PROMPT_WRITING_BASE, *parts])
        template_file = importlib.resources.files(package_path) / "main.mu"
        
        if not template_file.exists():
            raise FileNotFoundError(f"模板文件不存在: {template_id}/main.mu")
        
        return template_file.read_text(encoding='utf-8')
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise ValueError(f"无法加载模板: {template_id}")

def _find_template_path(template_id: str, template_folder: str = None) -> Path:
    """
    查找模板目录路径
    template_id: 可以是多层目录，如 'assistant' 或 'roles/teacher'
    template_folder: 外部模板文件夹路径
    """
    if not template_folder:
        raise ValueError("template_folder不能为空")
        
    template_path = Path(template_folder) / template_id
    if not template_path.is_dir():
        raise ValueError(f"无效的模板ID: {template_id}")
    
    return template_path

def _load_template_file(template_path: Path) -> str:
    """
    加载模板文件并处理嵌套引用
    template_path: 模板目录路径
    """
    main_file = template_path / "main.mu"
    logger.info(f"加载模板文件: {main_file}")
    if not main_file.exists():
        raise FileNotFoundError(f"main.mu文件不存在: {main_file}")
    
    with open(main_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 处理嵌套引用
    return _resolve_partials(content, template_path)

def _resolve_partials(content: str, base_path: Path) -> str:
    """
    解析模板中的嵌套引用
    content: 模板内容
    base_path: 基础路径，用于解析相对路径
    """
    def replace_partial(match):
        partial_name = match.group(1).strip()
        logger.info(f"解析部分模板: {partial_name}")
        
        if not partial_name.endswith('.mu'):
            partial_name += '.mu'
        
        partial_path = base_path / partial_name
        if not partial_path.exists():
            raise ValueError(f"无效的子模板标识: {partial_path}")
        
        with open(partial_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    # 只匹配部分模板语法 {{>name}}
    pattern = r'\{\{>\s*([^}]+)\s*\}\}'
    return re.sub(pattern, replace_partial, content)

@lru_cache(maxsize=128)
def load_prompt_template(template_id: str, template_folder: str = None) -> str:
    """
    加载提示语模板
    template_id: 模板目录名称，可以是多层目录，如 'assistant' 或 'roles/teacher'
    template_folder: 外部模板文件夹路径，如果为None则使用包内模板

    使用 load_prompt_template.cache_clear() 来刷新缓存
    """
    if template_folder:
        # 从本地文件夹加载
        template_path = _find_template_path(template_id, template_folder)
        try:
            return _load_template_file(template_path)
        except ValueError as e:
            # 保持ValueError不变
            raise
        except Exception as e:
            raise RuntimeError(f"加载模板 {template_id} 失败: {str(e)}")
    else:
        # 从包内资源加载
        try:
            return load_resource_template(template_id)
        except Exception as e:
            raise ValueError(f"无效的模板ID: {template_id}")

def clone_prompt_template(template_id: str, template_folder: str, force: bool = False):
    """
    克隆提示语模板。
    根据指定 template_id 将文件夹和文件拷贝到本地 template_folder 位置。
    
    如果已经存在，就不再覆盖已修改的模板成果。
    """
    template_path = Path(template_folder) / Path(template_id.replace('.', os.sep))
    template_path_str = str(template_path)

    # 如果已经存在，就不再覆盖已修改的模板成果。
    if template_path.exists():
        if force:
            shutil.rmtree(template_path)
        else:
            if any(template_path.iterdir()):
                raise ValueError(f"模板文件夹 [{template_path_str}] 非空！")

    template_path.mkdir(parents=True, exist_ok=True)

    normalized_template_id = template_id.replace(os.sep, '.')
    parts = normalized_template_id.split('.')
    if parts[-1] not in find_resource_template(*parts[:-1]):
        raise ValueError(f"<{template_id}> template_id 不存在！")

    def _get_template_str(res_file: str):
        resource_folder = f'{PROMPT_WRITING_BASE}.{normalized_template_id}'
        if is_resource(resource_folder, res_file):
            return read_text(resource_folder, res_file)
        resource_base = PROMPT_WRITING_BASE
        if is_resource(resource_base, res_file):
            return read_text(resource_base, res_file)
        return ''

    prompt_str = _get_template_str('main.mu')
    if not prompt_str:
        raise ValueError(f'main.mu 必须存在于 {template_id} 中！')

    main_mu_path = template_path / 'main.mu'
    with open(main_mu_path, 'w', encoding='utf-8') as f:
        f.write(prompt_str)

        # 保存替换 {{>include_name}} 变量文件
        matches = re.findall(r'{{>(.*?)}}', prompt_str)
        for part_name in matches:
            part_str = _get_template_str(f'{part_name.strip()}.mu')
            if part_str:
                part_mu_path = template_path / f'{part_name}.mu'
                with open(part_mu_path, 'w', encoding='utf-8') as pf:
                    pf.write(part_str)
            else:
                raise RuntimeError(f"无法在 {template_id} 中找到 {part_name}.mu")

    return template_path_str
