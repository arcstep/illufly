from typing import List
from importlib.resources import read_text, is_resource, contents
from langchain.prompts import PromptTemplate
from .config import (
    get_folder_root,
    get_folder_public,
    get_folder_prompts,
)
import os
import re
import json

PROMPT_WRITING_BASE = 'textlong.__PROMPTS__'

def find_resource_prompt(tag: str="writing"):
    """
    过滤出提示语模板所在的目录清单。
    """
    all_resources = contents(f'textlong.__PROMPTS__.{tag}')
    return [r for r in all_resources if not is_resource(f'{PROMPT_WRITING_BASE}.{tag}', r)]
 
def load_resource_prompt(prompt_id: str, tag: str="writing"):
    """
    从python包资源文件夹加载提示语模板。
    """
    if prompt_id not in find_resource_prompt(tag):
        raise ValueError(f"<{prompt_id}> prompt_id not exist !")

    def _get_prompt_str(res_file: str):
        if (res_folder := f'{PROMPT_WRITING_BASE}.{tag}.{prompt_id}') and is_resource(res_folder, res_file):
            return read_text(res_folder, res_file)
        elif (res_folder := f'{PROMPT_WRITING_BASE}.{tag}') and is_resource(res_folder, res_file):
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

def load_prompt(prompt_id: str, template_folder: str=None, tag: str="writing"):
    """
    从模板文件夹加载提示语模板。
    
    提示语模板中的约定：
    1. 提示语模板支持 f-string(*.txt) 和 mustache(*.mu) 两种语法
    2. 加载模板时，从模板路径开始寻找，如果找不到会向上查找文件，直至模板根文件夹
    3. 提示语模板的主文件是 main.txt 或 main.mu，如果都存在就优先用 main.mu
    4. 预处理 main.mu 中的 {{>include_name}} 语法
    5. 使用 PromptTemplate 和 core.utils.mustache 处理其他语法
       这包括 mustache 中的一般变量、partial变量和判断变量是否存在的逻辑等
    6. 变量命名时的约定
       - xxx__, 由系统内部的方法填写，请不要试图赋值
       - xxx_, 可选变量，加载时会被赋默认值""
       - xxx, 必须填写的变量
    """
    prompt_folder = os.path.join(
        get_folder_root(),
        template_folder or "",
        prompt_id
    )
    
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
        template = load_resource_prompt(prompt_id, tag)
        if template:
            return template

    raise ValueError(f'无法构建模板：{prompt_id}')

def save_prompt(template: PromptTemplate, prompt_id: str, template_folder: str=None):
    """
    保存提示语模板到文件夹。
    """
    prompt_folder = os.path.join(
        get_folder_root(),
        template_folder or get_folder_prompts(),
        prompt_id
    )
    os.makedirs(prompt_folder, exist_ok=True)
    
    ext = 'mu' if template.template_format == 'mustache' else 'txt'
    main_prompt = os.path.join(prompt_folder, f'main.{ext}')
    if main_prompt:
        with open(main_prompt, 'w', encoding='utf-8') as f:
            f.write(template.template)
            return True

    return False

def clone_prompt(prompt_id: str, template_folder: str=None, tag: str="writing"):
    """
    克隆提示语模板。
    根据指定的prompt_id，将文件夹和文件拷贝到template_folder位置。
    """
    if prompt_id not in find_resource_prompt(tag):
        raise ValueError(f"<{prompt_id}> prompt_id not exist !")

    prompt_folder = os.path.join(
        get_folder_root(),
        template_folder or get_folder_prompts(),
        prompt_id
    )
    os.makedirs(prompt_folder, exist_ok=True)

    def _copy_prompt_file(res_file: str):
        target_path = os.path.join(prompt_folder, res_file)
        txt = ''
        if (res_folder := f'{PROMPT_WRITING_BASE}.{tag}.{prompt_id}') and is_resource(res_folder, res_file):
            txt = read_text(res_folder, res_file)
        elif (res_folder := f'{PROMPT_WRITING_BASE}.{tag}') and is_resource(res_folder, res_file):
            txt = read_text(res_folder, res_file)
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(txt)
        return txt

    prompt_str = _copy_prompt_file('main.mu')

    # 保存 {{>include_name}} 变量
    include_dict = {}
    matches = re.findall(r'{{>(.*?)}}', prompt_str)
    for part_name in matches:
        _copy_prompt_file(f'{part_name.strip()}.mu')

    return True
