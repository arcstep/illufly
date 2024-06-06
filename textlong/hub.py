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
from .config import get_textlong_folder, _PROMPTS_FOLDER_NAME
import os
import json

def load_prompt(template_id: str):
    """
    task:
        - batch
        - summarise
        - write
        - ...
    template_id:
        - 扩写
        - 提纲
        - ...
    """
    resource_file = 'main.txt'
    resource_folder = f'textlong.prompts.{template_id}'
    if not is_resource(resource_folder, resource_file):
        resource_folder = f'textlong.prompts'
    
    prompt_str = read_text(resource_folder, resource_file)
    template = PromptTemplate.from_template(prompt_str)

    kwargs = {}
    for key in template.input_variables:
        resource_file = f'{key}.txt'
        resource_folder = f'textlong.prompts.{template_id}'
        kwargs[key] = read_text(resource_folder, resource_file) if is_resource(resource_folder, resource_file) else ''

    return template.partial(**kwargs)

def save_chat_prompt(template: ChatPromptTemplate, template_id: str, project_id: str="default", id="0", user_id="public"):
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
    prompt_path = os.path.join(get_textlong_folder(), user_id, project_id, _PROMPTS_FOLDER_NAME, id, template_id)

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

def load_chat_prompt(template_id: str, project_id: str="default", id: str="0", user_id: str="public", in_memory: bool=True):
    """
    加载提示语模板和partial变量的字符串。    
    目前不支持在partial中使用嵌套模板。
    """
    prompt_path = os.path.join(get_textlong_folder(), user_id, project_id, _PROMPTS_FOLDER_NAME, id, template_id)
    if in_memory and not os.path.exists(prompt_path):
        if template_id == "qa":
            from .qa import create_qa_prompt
            template = create_qa_prompt()
        elif template_id == "help":
            from .tree import create_writing_help_prompt
            template = create_writing_help_prompt()
        elif template_id == "init":
            from .tree import create_writing_init_prompt
            template = create_writing_init_prompt()
        elif template_id == "outline":
            from .tree import create_writing_todo_prompt
            template = create_writing_todo_prompt(content_type="outline")
        elif template_id == "paragraph":
            from .tree import create_writing_todo_prompt
            template = create_writing_todo_prompt(content_type="paragraph")
        else:
            raise ValueError(f"模板ID[{template_id}]不是内置模板！")
        
        return template

    messages = []
    partial_variables = {}

    for filename in sorted(os.listdir(prompt_path)):
        path = os.path.join(prompt_path, filename)

        message = None
        if filename.endswith('_system.json'):
            prompt = load_str_prompt(path)
            message = SystemMessagePromptTemplate.from_template(prompt.template, template_format='mustache')
        elif filename.endswith('_ai.json'):
            prompt = load_str_prompt(path)
            message = AIMessagePromptTemplate.from_template(prompt.template, template_format='mustache')
        elif filename.endswith('_human.json'):
            prompt = load_str_prompt(path)
            message = HumanMessagePromptTemplate.from_template(prompt.template, template_format='mustache')
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
