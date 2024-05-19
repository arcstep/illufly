from langchain.prompts import (
    ChatPromptTemplate,
    MessagesPlaceholder,
    SystemMessagePromptTemplate,
    AIMessagePromptTemplate,
    HumanMessagePromptTemplate,
    load_prompt as load_str_prompt,
)
from ..config import get_textlong_folder, _PROMPTS_FOLDER_NAME
from .writing_prompt import (
    create_writing_help_prompt,
    create_writing_init_prompt,
    create_writing_todo_prompt,
)
import os
import json

def save_chat_prompt(template: ChatPromptTemplate, template_id: str, project_id: str, id="0", user_id="default_user"):
    """
    保存提示语模板。
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

def load_chat_prompt(template_id: str, project_id: str=None, id="0", user_id="default_user"):
    """
    加载提示语模板和partial变量的字符串。    
    目前不支持在partial中使用嵌套模板。
    """
    if project_id == None:
        if template_id == "help":
            return create_writing_help_prompt()
        elif template_id == "init":
            return create_writing_init_prompt()
        elif template_id == "outline":
            return create_writing_todo_prompt(content_type="outline")
        elif template_id == "paragraph":
            return create_writing_todo_prompt(content_type="paragraph")
        else:
            raise ValueError(f"模板ID必须为 [init|outline|paragraph|help] 中的一个, [{template_id}]不能支持！")

    prompt_path = os.path.join(get_textlong_folder(), user_id, project_id, _PROMPTS_FOLDER_NAME, id, template_id)
    if not os.path.exists(prompt_path):
        raise FileNotFoundError(f"提示语模板 {template_id} 不存在")

    messages = []
    partial_variables = {}

    for filename in sorted(os.listdir(prompt_path)):
        path = os.path.join(prompt_path, filename)

        message = None
        if filename.endswith('_system.json'):
            prompt = load_str_prompt(path)
            message = SystemMessagePromptTemplate.from_template(prompt.template)
        elif filename.endswith('_ai.json'):
            prompt = load_str_prompt(path)
            message = AIMessagePromptTemplate.from_template(prompt.template)
        elif filename.endswith('_human.json'):
            prompt = load_str_prompt(path)
            message = HumanMessagePromptTemplate.from_template(prompt.template)
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
