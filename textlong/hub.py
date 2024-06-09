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
    get_textlong_folder,
    get_default_public,
    _PROMPTS_STRING_FOLDER_NAME,
    _PROMPTS_CHAT_FOLDER_NAME,
)
import os
import json

def load_resource_prompt(prompt_id: str):
    """
    从python包资源文件夹加载提示语模板。
    
    prompt_id: OUTLINE | OUTLINE_DETAIL
    """
    resource_file = 'main.txt'
    resource_folder = f'textlong.prompts.{prompt_id}'
    if not is_resource(resource_folder, resource_file):
        resource_folder = f'textlong.prompts'
    
    prompt_str = read_text(resource_folder, resource_file)
    template = PromptTemplate.from_template(prompt_str)

    kwargs = {}
    for key in template.input_variables:
        resource_file = f'{key}.txt'
        resource_folder = f'textlong.prompts.{prompt_id}'
        kwargs[key] = read_text(resource_folder, resource_file) if is_resource(resource_folder, resource_file) else ''

    return template.partial(**kwargs)

def load_string_prompt(prompt_id: str, user_id: str=None):
    """
    从文件夹加载提示语模板。
    """
    prompt_folder = os.path.join(
        get_textlong_folder(),
        user_id or get_default_public(),
        _PROMPTS_CHAT_FOLDER_NAME,
        prompt_id
    )
    
    main_prompt = os.path.join(prompt_folder, 'main.txt')
    if os.path.exists(main_prompt):
        with open(main_prompt, 'r') as f:
            prompt_str = f.read()
            template = PromptTemplate.from_template(prompt_str)

            kwargs = {}
            for key in template.input_variables:
                var_prompt = os.path.join(prompt_folder, f'{key}.txt')
                prompt_str_var = ''
                with open(var_prompt, 'r') as var:
                    prompt_str_var = var.read()
                kwargs[key] = prompt_str_var

            return template.partial(**kwargs)

    return load_resource_prompt(prompt_id)

def save_string_prompt(template: PromptTemplate, prompt_id: str, user_id: str=None):
    """
    保存提示语模板到文件夹。
    """
    prompt_folder = os.path.join(
        get_textlong_folder(),
        user_id or get_default_public(),
        _PROMPTS_CHAT_FOLDER_NAME,
        prompt_id
    )
    os.makedirs(prompt_folder, exist_ok=True)
    
    main_prompt = os.path.join(prompt_folder, 'main.txt')
    if main_prompt:
        with open(main_prompt, 'w', encoding='utf-8') as f:
            f.write(template.template)

    for k, v in template.partial_variables.items():
        if v != None:
            path = os.path.join(prompt_path, f"var_{k}.txt")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(v)

def load_chat_prompt(template: ChatPromptTemplate, prompt_id: str, user_id=None):
    """
    加载提示语模板和partial变量的字符串。    
    目前不支持在partial中使用嵌套模板。
    """
    prompt_path = os.path.join(
        get_textlong_folder(),
        user_id or get_default_public(),
        _PROMPTS_CHAT_FOLDER_NAME,
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
        elif filename.startswith('var_') and filename.endswith('.md'):
            with open(path, 'r') as f:
                text = f.read()
                var_name = filename[4:-3]
                partial_variables[var_name] = int(text) if text.isdigit() else text
        else:
            continue

        if message:
            messages.append(message)

    return ChatPromptTemplate.from_messages(messages=messages).partial(**partial_variables)

def save_chat_prompt(template: ChatPromptTemplate, prompt_id: str, user_id=None):
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
        get_textlong_folder(),
        user_id or get_default_public(),
        _PROMPTS_FOLDER_NAME,
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

    for k, v in template.partial_variables.items():
        if v != None:
            path = os.path.join(prompt_path, f"var_{k}.md")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(f'{v}')
