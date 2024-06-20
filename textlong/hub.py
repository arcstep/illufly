from typing import List
from importlib.resources import read_text, is_resource
from langchain.prompts import (
    PromptTemplate,
    ChatPromptTemplate,
    MessagesPlaceholder,
    SystemMessagePromptTemplate,
    AIMessagePromptTemplate,
    HumanMessagePromptTemplate,
    load_prompt as load_str_prompt,
)
from .config import (
    get_folder_root,
    get_folder_public,
    get_folder_prompts_string,
    get_folder_prompts_chat,
)
import os
import re
import json

def find_resource_promopt():
    """
    列举包内的所有提示语模板的资源类型、适用方法和名称。
    
    如果要将包内提示语模板保存到本地，可以向这样使用：
    ```python
    prompt = load_resource_prompt("IDEA)
    save_string_template(prompt, "MY_IDEA")
    ```
    """
    return {
        "from_idea": [
            ("STRING_TEMPLATE", "IDEA"),
            ("STRING_TEMPLATE", "OUTLINE")
        ],
        "from_outline": [
            ("STRING_TEMPLATE", "OUTLINE_DETAIL"),
            ("STRING_TEMPLATE", "OUTLINE_SELF")
        ],
        "from_chunk": [
            ("STRING_TEMPLATE", "REWRITE"),
            ("STRING_TEMPLATE", "TRANSLATE")
        ],
        "extract": [
            ("STRING_TEMPLATE", "SUMMARISE"),
            ("STRING_TEMPLATE", "SUMMARISE_TECH"),
        ],
    }

def load_resource_prompt(action: str, prompt_id: str):
    """
    从python包资源文件夹加载提示语模板。
    """
    resource_file = 'main.txt'
    resource_folder = f'textlong.__PROMPTS__.{action}.{prompt_id}'
    if not is_resource(resource_folder, resource_file):
        resource_folder = f'textlong.__PROMPTS__'
    
    prompt_str = read_text(resource_folder, resource_file)
    template = PromptTemplate.from_template(prompt_str)

    kwargs = {}
    for key in template.input_variables:
        resource_file = f'{key}.txt'
        resource_folder = f'textlong.__PROMPTS__.{action}.{prompt_id}'
        kwargs[key] = read_text(resource_folder, resource_file) if is_resource(resource_folder, resource_file) else ''

    return template.partial(**kwargs)

def _find_prompt_file(prompt_id: str, file_name, template_folder: str=None, sep: str="/", all_path: List[str]=[]):
    prompt_id = prompt_id.strip(f'{sep}| ')
    prompt_folder = os.path.join(get_folder_root(), template_folder or "", prompt_id)

    for ext in ['mu', 'mustache', 'txt']:
        if (file_path := os.path.join(prompt_folder, f'{file_name}.{ext}')) and os.path.exists(file_path):
            return file_path

    all_path.append(prompt_folder)
    if not prompt_id:
        raise ValueError(f"Can't find {file_name}(.mu, .mustache, .txt) in [ {', '.join(all_path)} ]!")
    return _find_prompt_file(prompt_id.rpartition(sep)[0], file_name, template_folder, sep, all_path)

def load_prompt(prompt_id: str, template_folder: str=None):
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
       - __xxx, 由系统内部的方法填写，请不要试图赋值
       - _xxx, 可选变量，加载时会被赋默认值""
       - xxx, 必须填写的变量
    """
    prompt_folder = os.path.join(
        get_folder_root(),
        template_folder or "",
        prompt_id
    )
    
    main_prompt = _find_prompt_file(prompt_id, 'main', template_folder)
    template_format = 'mustache' if main_prompt.endswith('.mu') or  main_prompt.endswith('.mustache') else 'f-string'

    with open(main_prompt, 'r') as f:
        prompt_str = f.read()

        if template_format == 'mustache':
            # 替换 {{>include_name}} 变量
            include_dict = {}
            matches = re.findall(r'{{>(.*?)}}', prompt_str)
            for part_name in matches:
                part_file = _find_prompt_file(prompt_id, part_name, template_folder)
                with open(part_file, 'r') as f:
                    include_dict[part_name] = f.read()
            for part_name, part_str in include_dict.items():
                prompt_str = prompt_str.replace("{{>" + part_name + "}}", part_str)

        template = PromptTemplate.from_template(prompt_str, template_format=template_format)

        kwargs = {}
        for key in template.input_variables:
            if key.startswith('_'):
                kwargs[key] = ''

        return template.partial(**kwargs)

    raise ValueError(f'无法构建模板：{prompt_id}')

def load_string_prompt(action: str, prompt_id: str, template_folder: str=None):
    """
    从文件夹加载提示语模板。
    """
    prompt_folder = os.path.join(
        get_folder_root(),
        template_folder or "",
        get_folder_prompts_string(action),
        prompt_id
    )
    
    main_prompt = os.path.join(prompt_folder, 'main.txt')
    if not os.path.exists(main_prompt):
        prompt_template = load_resource_prompt(action, prompt_id)
        save_string_prompt(prompt_template, action, prompt_id, template_folder=template_folder)

    if os.path.exists(main_prompt):
        with open(main_prompt, 'r') as f:
            prompt_str = f.read()
            template = PromptTemplate.from_template(prompt_str)

            kwargs = {}
            for key in template.input_variables:
                var_prompt_path = os.path.join(prompt_folder, f'{key}.txt')
                prompt_var = ''
                if os.path.exists(var_prompt_path):
                    with open(var_prompt_path, 'r') as var:
                        prompt_var = var.read()
                kwargs[key] = prompt_var

            return template.partial(**kwargs)

    raise ValueError(f'无法构建模板：{action} / {prompt_id}')

def save_string_prompt(template: PromptTemplate, action: str, prompt_id: str, template_folder: str=None):
    """
    保存提示语模板到文件夹。
    """
    prompt_folder = os.path.join(
        get_folder_root(),
        template_folder or "",
        get_folder_prompts_string(action),
        prompt_id
    )
    os.makedirs(prompt_folder, exist_ok=True)
    
    main_prompt = os.path.join(prompt_folder, 'main.txt')
    if main_prompt:
        with open(main_prompt, 'w', encoding='utf-8') as f:
            f.write(template.template)

    for k, v in template.partial_variables.items():
        if v != None and len(v) > 0:
            path = os.path.join(prompt_folder, f"{k}.txt")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(v)
    
    return True

def load_chat_prompt(action: str, prompt_id: str, template_folder: str=None):
    """
    加载提示语模板和partial变量的字符串。    
    目前不支持在partial中使用嵌套模板。
    """
    prompt_path = os.path.join(
        get_folder_root(),
        template_folder or "",
        get_folder_prompts_chat(action),
        prompt_id
    )

    messages = []
    partial_variables = {}

    # 'f-string' or 'mustache'
    template_format = 'f-string' 

    for filename in sorted(os.listdir(prompt_path)):
        path = os.path.join(prompt_path, filename)

        message = None
        if filename.endswith('_system.json'):
            prompt = load_str_prompt(path)
            message = SystemMessagePromptTemplate.from_template(prompt.template, template_format=template_format)
        elif filename.endswith('_ai.json'):
            prompt = load_str_prompt(path)
            message = AIMessagePromptTemplate.from_template(prompt.template, template_format=template_format)
        elif filename.endswith('_human.json'):
            prompt = load_str_prompt(path)
            message = HumanMessagePromptTemplate.from_template(prompt.template, template_format=template_format)
        elif filename.endswith('_placeholder.json'):
            with open(path, 'r') as f:
                data = json.load(f)
                message = MessagesPlaceholder(**data)
        elif filename.endswith('.txt'):
            with open(path, 'r') as f:
                text = f.read()
                var_name = filename[:-3]
                partial_variables[var_name] = int(text) if text.isdigit() else text
        else:
            continue

        if message:
            messages.append(message)

    return ChatPromptTemplate.from_messages(messages=messages).partial(**partial_variables)

def save_chat_prompt(template: ChatPromptTemplate, action: str, prompt_id: str, template_folder: str=None):
    """
    保存对话风格的提示语模板。

    提示语模板中的每一段对话和局部变量都会被保存为独立的`json`格式。
    具体规则如下：
        - 系统提示，`{对话序号}_system.json`
        - 大模型消息，`{对话序号}_ai.json`
        - 人类消息，`{对话序号}_human.json`
        - 占位消息，`{对话序号}_placeholder.json`
        - `partial`变量，`var_{变量名}.md`
    """
    prompt_path = os.path.join(
        get_folder_root(),
        template_folder or "",
        get_folder_prompts_chat(action),
        prompt_id
    )

    for i, p in enumerate(template.messages):
        if isinstance(p, SystemMessagePromptTemplate):
            path = os.path.join(prompt_path, f"{i}_system.json")
        elif isinstance(p, AIMessagePromptTemplate):
            path = os.path.join(prompt_path, f"{i}_ai.json")
        elif isinstance(p, HumanMessagePromptTemplate):
            path = os.path.join(prompt_path, f"{i}_human.json")
        elif isinstance(p, MessagesPlaceholder):
            path = os.path.join(prompt_path, f"{i}_placeholder.json")

        if path:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                if isinstance(p, MessagesPlaceholder):
                    json.dump(p.dict(), f, indent=4, ensure_ascii=False)
                else:
                    json.dump(p.prompt.dict(), f, indent=4, ensure_ascii=False)

    for key, var in template.partial_variables.items():
        if var != None:
            path = os.path.join(prompt_path, f"{key}.txt")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(var)
