from langchain.prompts import (
    ChatPromptTemplate,
    MessagesPlaceholder,
    SystemMessagePromptTemplate,
    AIMessagePromptTemplate,
    HumanMessagePromptTemplate,
    load_prompt as load_str_prompt,
)
from ..config import get_textlong_folder, _PROMPTS_FOLDER_NAME
import os
import json

def save_chat_prompt(template: ChatPromptTemplate, template_id: str, project_id: str, id="0"):
    """
    保存提示语模板。
    """
    prompt_path = os.path.join(get_textlong_folder(), project_id, _PROMPTS_FOLDER_NAME, id, template_id)

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

def load_chat_prompt(template_id: str, project_id: str, id="0"):
    """
    加载提示语模板和partial变量的字符串。    
    目前不支持在partial中使用嵌套模板。
    """
    prompt_path = os.path.join(get_textlong_folder(), project_id, _PROMPTS_FOLDER_NAME, id, template_id)
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
