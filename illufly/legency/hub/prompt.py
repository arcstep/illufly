"""
    提示语模板采用了`mustache`语法，这是一种逻辑无关的模板语法，包括以下特性：
    1. **变量替换**：使用`{{variable}}`来插入变量的值。
    2. **注释**：使用`{{! comment }}`来添加不会在渲染结果中显示的注释。
    3. **条件判断**：使用`{{#condition}}{{/condition}}`来进行条件判断，如果条件为真，则渲染内部的内容。
    4. **部分模板**：使用`{{> partial}}`来包含另一个模板文件。
    ... 还有其他一些可用的特性
"""

from typing import List, Dict, Any, Union, Set
from importlib.resources import read_text, is_resource, contents
from chevron.renderer import render as mustache_render
from chevron.tokenizer import tokenize as mustache_tokenize
from ..config import get_env

import os
import re
import json
from pathlib import Path

PROMPT_WRITING_BASE = 'illufly.__PROMPT_TEMPLATES__'

def find_resource_template(*seg_path):
    """
    过滤出提示语模板所在的目录清单。
    """
    package_path = ".".join([PROMPT_WRITING_BASE, *seg_path])
    all_resources = contents(package_path)
    return [r for r in all_resources if not is_resource(PROMPT_WRITING_BASE, r)]

def load_resource_template(template_id: str):
    """
    从python包资源文件夹加载提示语模板。
    """
    normalized_template_id = template_id.replace(os.sep, '.').replace('/', '.')
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

    # 替换 {{>include_name}} 变量
    include_dict = {}
    matches = re.findall(r'{{>(.*?)}}', prompt_str)
    for part_name in matches:
        included_str = _get_template_str(f'{part_name.strip()}.mu')
        if included_str:
            include_dict[part_name] = included_str
        else:
            raise RuntimeError(f"无法在 {template_id} 中找到 {part_name}.mu！")
    for part_name, part_str in include_dict.items():
        prompt_str = prompt_str.replace(f"{{>{part_name}}}", part_str)

    return prompt_str

def _find_prompt_file(template_id: str, file_name: str, template_folder: str = None, sep: str = None, all_path: List[str] = None, force: bool = False):
    sep = sep or os.sep
    if all_path is None:
        all_path = []
    normalized_template_id = template_id.replace('/', sep).strip(f'{sep} ').replace('\\', sep)

    prompt_folder = Path(template_folder or "") / Path(normalized_template_id)
    prompt_folder = prompt_folder.as_posix() if sep != os.sep else str(prompt_folder)

    for ext in ['mu', 'mustache', 'txt']:
        file_path = prompt_folder / f'{file_name}.{ext}' if isinstance(prompt_folder, Path) else os.path.join(prompt_folder, f'{file_name}.{ext}')
        if os.path.exists(file_path):
            return file_path

    all_path.append(prompt_folder)
    if not normalized_template_id:
        if force:
            raise ValueError(f"无法在 [ {', '.join(all_path)} ] 中找到 {file_name}(.mu, .mustache, .txt) 文件！")
        else:
            return None
    parent_id = Path(normalized_template_id).parent
    return _find_prompt_file(parent_id.as_posix() if sep != os.sep else parent_id.name, file_name, template_folder, sep, all_path, force)

def load_prompt_template(template_id: str, template_folder: str = None):
    """
    从模板文件夹加载提示语模板。

    提示语模板中的约定：
    1. 加载模板时，从模板路径开始寻找，如果找不到会向上查找文件，直至模板根文件夹
    2. 提示语模板的主文件是 main.mu
    3. 预处理 main.mu 中的 {{>include_name}} 语法
    4. 如果找不到 main.mu 文件，则从资源文件夹中加载
    """
    main_prompt = _find_prompt_file(template_id, 'main', template_folder)

    if main_prompt:
        with open(main_prompt, 'r', encoding='utf-8') as f:
            prompt_str = f.read()

            # 替换 {{>include_name}} 变量
            include_dict = {}
            matches = re.findall(r'{{>(.*?)}}', prompt_str)
            for part_name in matches:
                part_file = _find_prompt_file(template_id, part_name.strip(), template_folder)
                if part_file:
                    with open(part_file, 'r', encoding='utf-8') as pf:
                        include_dict[part_name] = pf.read()
                else:
                    raise RuntimeError(f"无法找到包含文件 {part_name}.mu")
            for part_name, part_str in include_dict.items():
                prompt_str = prompt_str.replace(f"{{>{part_name}}}", part_str)

            return prompt_str
    else:
        prompt_str = load_resource_template(template_id)
        if prompt_str:
            return prompt_str

    raise ValueError(f'无法构建模板：{template_id}')

def get_template_variables(template_text: str):
    vars: Set[str] = set()
    section_depth = 0
    for token_type, key in mustache_tokenize(template_text):
        if token_type == "end":
            section_depth -= 1
        elif (
            token_type in ("variable", "section", "inverted section", "no escape")
            and key != "."
            and section_depth == 0
        ):
            vars.add(key.split(".")[0])
        if token_type in ("section", "inverted section"):
            section_depth += 1
    return vars

def clone_prompt_template(template_id: str, template_folder: str = None):
    """
    克隆提示语模板。
    根据指定 template_id 将文件夹和文件拷贝到本地 template_folder 位置。
    
    如果已经存在，就不再覆盖已修改的模板成果。
    """
    local_folder = Path(template_folder or get_env("ILLUFLY_PROMPT_TEMPLATE_LOCAL_FOLDER"))
    template_path = local_folder / Path(template_id.replace('.', os.sep))
    template_path_str = str(template_path)

    # 如果已经存在，就不再覆盖已修改的模板成果。
    if template_path.exists():
        if any(template_path.iterdir()):
            raise ValueError(f"模板文件夹 [{template_path_str}] 非空！")
    else:
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
