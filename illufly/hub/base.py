"""
    提示语模板采用了`mustache`语法，这是一种逻辑无关的模板语法，包括以下特性：
    1. **变量替换**：使用`{{variable}}`来插入变量的值。
    2. **注释**：使用`{{! comment }}`来添加不会在渲染结果中显示的注释。
    3. **条件判断**：使用`{{#condition}}{{/condition}}`来进行条件判断，如果条件为真，则渲染内部的内容。
    4. **部分模板**：使用`{{> partial}}`来包含另一个模板文件。
    ... 还有其他一些可用的特性
"""

from typing import List, Dict, Any, Union
from importlib.resources import read_text, is_resource, contents
from chevron.renderer import render as mustache_render
from chevron.tokenizer import tokenize as mustache_tokenize
from ..config import get_folder_root, get_env

import os
import re
import json

PROMPT_WRITING_BASE = 'illufly.__PROMPT_TEMPLATES__'

def find_resource_template(*seg_path):
    """
    过滤出提示语模板所在的目录清单。
    """

    all_resources = contents(".".join([PROMPT_WRITING_BASE, *seg_path]))
    return [r for r in all_resources if not is_resource(f'{PROMPT_WRITING_BASE}', r)]

def load_resource_template(template_id: str):
    """
    从python包资源文件夹加载提示语模板。
    """
    template_id = template_id.replace(os.sep, '.')
    parts = template_id.split('.')
    if parts[-1] not in find_resource_template(*parts[:-1]):
        raise ValueError(f"<{template_id}> template_id not exist !")

    def _get_template_str(res_file: str):
        if (res_folder := f'{PROMPT_WRITING_BASE}.{template_id}') and is_resource(res_folder, res_file):
            return read_text(res_folder, res_file)
        elif (res_folder := f'{PROMPT_WRITING_BASE}') and is_resource(res_folder, res_file):
            return read_text(res_folder, res_file)
        else:
            return ''

    prompt_str = _get_template_str('main.mu')

    # 替换 {{>include_name}} 变量
    include_dict = {}
    matches = re.findall(r'{{>(.*?)}}', prompt_str)
    for part_name in matches:
        prmopt_str = _get_template_str(f'{part_name.strip()}.mu')
        if prmopt_str:
            include_dict[part_name] = prmopt_str
    for part_name, part_str in include_dict.items():
        prompt_str = prompt_str.replace("{{>" + part_name + "}}", part_str)

    return prompt_str

def _find_prompt_file(template_id: str, file_name, template_folder: str=None, sep: str=None, all_path: List[str]=[], force: bool=False):
    sep = sep or os.sep
    template_id = template_id.strip(f'{sep}| ')

    prompt_folder = os.path.join(get_folder_root(), template_folder or "", template_id)
    if sep != os.sep:
        prompt_folder = prompt_folder.replace(os.sep, sep).strip(sep)

    for ext in ['mu', 'mustache', 'txt']:
        if (file_path := os.path.join(prompt_folder, f'{file_name}.{ext}')) and os.path.exists(file_path):
            return file_path

    all_path.append(prompt_folder)
    if not template_id:
        if force:
            raise ValueError(f"Can't find {file_name}(.mu, .mustache, .txt) in [ {', '.join(all_path)} ]!")
        else:
            return None
    return _find_prompt_file(template_id.rpartition(sep)[0], file_name, template_folder, sep, all_path)

def load_template(template_id: str, template_folder: str=None,):
    """
    从模板文件夹加载提示语模板。

    提示语模板中的约定：
    1. 加载模板时，从模板路径开始寻找，如果找不到会向上查找文件，直至模板根文件夹
    2. 提示语模板的主文件是 main.mu
    3. 预处理 main.mu 中的 {{>include_name}} 语法
    4. 如果找不到 main.mu 文件，则从资源文件夹中加载
    """
    template_folder = template_folder or get_env("ILLUFLY_TEMPLATE_LOCAL_FOLDER")
    main_prompt = _find_prompt_file(template_id, 'main', template_folder)

    if main_prompt:
        with open(main_prompt, 'r') as f:
            prompt_str = f.read()

            # 替换 {{>include_name}} 变量
            include_dict = {}
            matches = re.findall(r'{{>(.*?)}}', prompt_str)
            for part_name in matches:
                part_file = _find_prompt_file(template_id, part_name.strip(), template_folder)
                with open(part_file, 'r') as f:
                    include_dict[part_name] = f.read()
            for part_name, part_str in include_dict.items():
                prompt_str = prompt_str.replace("{{>" + part_name + "}}", part_str)

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

def clone_prompt(template_id: str, template_folder: str=None):
    """
    克隆提示语模板。
    根据指定 template_id 将文件夹和文件拷贝到本地 template_folder 位置。
    
    如果已经存在，就不再覆盖已修改的模板成果。
    """
    template_path = os.path.join(
        template_folder or get_env("ILLUFLY_TEMPLATE_LOCAL_FOLDER"),
        template_id.replace('.', os.sep)
    )

    # 如果已经存在，就不再覆盖已修改的模板成果。
    if os.path.exists(template_path):
        files = os.listdir(template_path)
        if files:
            raise ValueError(f"template_folder [{template_path}] not empty !")

    # 确保 template_id 是有效的
    template_id = template_id.replace(os.sep, '.')
    parts = template_id.split('.')
    if parts[-1] not in find_resource_template(*parts[:-1]):
        raise ValueError(f"<{template_id}> template_id not exist !")

    # 如果模板不存在，则创建目录
    os.makedirs(template_path, exist_ok=True)

    def _get_template_str(res_file: str):
        if (res_folder := f'{PROMPT_WRITING_BASE}.{template_id}') and is_resource(res_folder, res_file):
            return read_text(res_folder, res_file)
        elif (res_folder := f'{PROMPT_WRITING_BASE}') and is_resource(res_folder, res_file):
            return read_text(res_folder, res_file)
        else:
            return ''

    prompt_str = _get_template_str('main.mu')
    if not prompt_str:
        raise ValueError(f'main.mu MUST exist in {template_id} !')
    
    with open(os.path.join(template_path, 'main.mu'), 'w') as f:
        f.write(prompt_str)

        # 保存替换 {{>include_name}} 变量文件
        matches = re.findall(r'{{>(.*?)}}', prompt_str)
        for part_name in matches:
            prmopt_str = _get_template_str(f'{part_name.strip()}.mu')
            if prmopt_str:
                with open(os.path.join(template_path, f'{part_name}.mu'), 'w') as f:
                    f.write(prmopt_str)

    return template_path
