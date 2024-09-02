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
from langchain.prompts import PromptTemplate

import os
import re
import json

from ..config import get_folder_root, get_env

PROMPT_WRITING_BASE = 'textlong.__CHAT_TEMPLATES__'
def find_resource_prompt():
    """
    过滤出提示语模板所在的目录清单。
    """

    all_resources = contents(f'{PROMPT_WRITING_BASE}')
    return [r for r in all_resources if not is_resource(f'{PROMPT_WRITING_BASE}', r)]


def load_resource_chat_template(prompt_id: str):
    """
    从python包资源文件夹加载提示语模板。
    """
    if prompt_id not in find_resource_prompt():
        raise ValueError(f"<{prompt_id}> prompt_id not exist !")

    def _get_prompt_str(res_file: str):
        if (res_folder := f'{PROMPT_WRITING_BASE}.{prompt_id}') and is_resource(res_folder, res_file):
            return read_text(res_folder, res_file)
        elif (res_folder := f'{PROMPT_WRITING_BASE}') and is_resource(res_folder, res_file):
            return read_text(res_folder, res_file)
        else:
            return ''

    prompt_str = _get_prompt_str('main.mu')

    # 替换 {{>include_name}} 变量
    include_dict = {}
    matches = re.findall(r'{{>(.*?)}}', prompt_str)
    for part_name in matches:
        prmopt_str = _get_prompt_str(f'{part_name.strip()}.mu')
        if prmopt_str:
            include_dict[part_name] = prmopt_str
    for part_name, part_str in include_dict.items():
        prompt_str = prompt_str.replace("{{>" + part_name + "}}", part_str)

    template = PromptTemplate.from_template(prompt_str, template_format='mustache')

    kwargs = {}
    for key in template.input_variables:
        if key.endswith('_'):
            kwargs[key] = ''

    return template.partial(**kwargs)

def _find_prompt_file(prompt_id: str, file_name, template_folder: str=None, sep: str=None, all_path: List[str]=[], force: bool=False):
    sep = sep or os.sep
    prompt_id = prompt_id.strip(f'{sep}| ')

    prompt_folder = os.path.join(get_folder_root(), template_folder or "", prompt_id)
    if sep != os.sep:
        prompt_folder = prompt_folder.replace(os.sep, sep).strip(sep)

    for ext in ['mu', 'mustache', 'txt']:
        if (file_path := os.path.join(prompt_folder, f'{file_name}.{ext}')) and os.path.exists(file_path):
            return file_path

    all_path.append(prompt_folder)
    if not prompt_id:
        if force:
            raise ValueError(f"Can't find {file_name}(.mu, .mustache, .txt) in [ {', '.join(all_path)} ]!")
        else:
            return None
    return _find_prompt_file(prompt_id.rpartition(sep)[0], file_name, template_folder, sep, all_path)

def load_chat_template(prompt_id: str, template_folder: str=None,):
    """
    从模板文件夹加载提示语模板。
    
    提示语模板中的约定：
    1. 尽管资源库中只使用 mustache 语法的模板，但自定义模板同时支持 f-string(*.txt) 和 mustache(*.mu) 两种语法
    2. 加载模板时，从模板路径开始寻找，如果找不到会向上查找文件，直至模板根文件夹
    3. 提示语模板的主文件是 main.txt 或 main.mu，如果都存在就优先用 main.mu
    4. 预处理 main.mu 中的 {{>include_name}} 语法
    5. 使用 PromptTemplate 和 core.utils.mustache 处理其他语法
        - 这包括 mustache 中的一般变量、partial变量和判断变量是否存在的逻辑等
    6. 变量命名时的约定
        - xxx__, 由系统内部的方法填写，请不要试图赋值（即使你手工赋值，也会被内部逻辑覆盖）
        - xxx_, 可选变量，加载时会被赋默认值为：""
        - xxx, 必须填写的变量
    """
    template_folder = template_folder or get_env("TEXTLONG_PROMPTS")
    main_prompt = _find_prompt_file(prompt_id, 'main', template_folder)

    if main_prompt:
        template_format = 'mustache' if main_prompt.endswith('.mu') or  main_prompt.endswith('.mustache') else 'f-string'
        with open(main_prompt, 'r') as f:
            prompt_str = f.read()

            if template_format == 'mustache':
                # 替换 {{>include_name}} 变量
                include_dict = {}
                matches = re.findall(r'{{>(.*?)}}', prompt_str)
                for part_name in matches:
                    part_file = _find_prompt_file(prompt_id, part_name.strip(), template_folder)
                    with open(part_file, 'r') as f:
                        include_dict[part_name] = f.read()
                for part_name, part_str in include_dict.items():
                    prompt_str = prompt_str.replace("{{>" + part_name + "}}", part_str)

            template = PromptTemplate.from_template(prompt_str, template_format=template_format)

            kwargs = {}
            for key in template.input_variables:
                if key.endswith('_'):
                    kwargs[key] = ''

            return template.partial(**kwargs)
    else:
        template = load_resource_chat_template(prompt_id)
        if template:
            return template

    raise ValueError(f'无法构建模板：{prompt_id}')
