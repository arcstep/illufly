import os
import sys
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)

import gradio as gr
import json
from illufly.flow import Team, ReAct
from illufly.chat import ChatQwen, FakeLLM
from illufly.utils import escape_xml_tags
from illufly.toolkits import WebSearch, Text2ImageWanx, CogView, PandasAgent, Now
import pandas as pd

# ChatAgent
qwen = ChatQwen(name="通义千问")
fake = FakeLLM(name="FakeLLM", sleep=0.3)
react = ReAct(
    planner=ChatQwen(
        tools=[
            WebSearch(name="互联网搜索"),
            Now(name="时钟")
        ]
    ),
    name="ReAct 长推理"
)
team = Team(agents=[qwen, fake, react], name="团队协作")

all_agents = [qwen, fake, react, team]

def select_agent(agent_name):
    print("select_agent >>>", agent_name)
    agents = {agent.name: agent for agent in all_agents}
    return agents.get(agent_name, None)

def bot(agent_name, prompt: str, hist: list, state: dict):
    agent = select_agent(agent_name)
    try:
        resp = ""
        final_hist = hist
        blocks = agent(state.get("prompt", "hi"), generator="sync", verbose=True)
        for block in blocks:
            if isinstance(block, dict):
                if block.get("data", None):
                    if block["data"].get("block_type", None) in ["text", "chunk", "tool_resp_text", "tool_resp_chunk"]:
                        resp += block["data"]["content"]
                        final_hist = hist + [{"role": "assistant", "content": escape_xml_tags(resp)}]
                        yield final_hist
            else:
                raise ValueError(f"Unknown block type: {type(block)}")
    except IndexError as e:
        print("Error: No content returned from agent.", e)
        final_hist.append({"role": "assistant", "content": "No response available."})
    return final_hist

def get_list_data():
    # 示例数据
    items = [
        {"name": "Item 1", "link": "#"},
        {"name": "Item 2", "link": "#"},
        {"name": "Item 3", "link": "#"}
    ]
    return items

with gr.Blocks() as main_ui:
    gr.Markdown("# 🌈 小虹 AI")
    state = gr.State()

    with gr.Row():
        with gr.Column(scale=1):
            agent_list = gr.Dropdown(
                choices=[agent.name for agent in all_agents],
                label="选择智能体",
                value=qwen.name
            )
            agent_config = gr.Textbox(label="智能体配置")
            
            # 使用 HTML 组件来显示可点击的列表
            list_items = get_list_data()
            list_html = "<ul>" + "".join(
                f'<li><a href="{item["link"]}" onclick="reloadChatHistory(\'{item["name"]}\'); return false;">{item["name"]}</a></li>'
                for item in list_items
            ) + "</ul>"
            gr.HTML(list_html)

            clear = gr.Button("开始新对话")

        with gr.Column(scale=4):
            user_avatar_path = os.path.join(os.getcwd(), "icon/user.png")
            qwen_avatar_path = os.path.join(os.getcwd(), "icon/qwen.png")

            chat_history = gr.Chatbot(
                type="messages", 
                label="聊天记录",
                avatar_images=(user_avatar_path, qwen_avatar_path),
            )
            user_input = gr.Textbox(label="输入消息")

            user_input.submit(
                lambda prompt, hist: ("", hist + [{"role": "user", "content": prompt}], {"prompt": prompt}),
                [user_input, chat_history],
                [user_input, chat_history, state],
                queue=False
            ).then(
                bot,
                [agent_list, user_input, chat_history, state],
                chat_history
            )

        clear.click(lambda: None, None, chat_history, queue=False)

    # 添加自定义 CSS 和 JavaScript
    gr.HTML("""
    <style>
        footer{display:none !important}
        body {
            font-family: Arial, sans-serif;
        }
        .avatar-container.svelte-1x5p6hu:not(.thumbnail-item) img {
            margin: 0;
            padding: 0;
        }
    </style>
    <script>
        function reloadChatHistory(itemName) {
            // 在这里实现重新加载聊天历史的逻辑
            console.log("Reload chat history for:", itemName);
            // 你可以在这里调用 Gradio 的 Python 函数来更新聊天记录
        }
    </script>
    <div style="text-align: center; padding: 10px; background-color: var(--background-secondary); color: var(--text-color);">
        <p>✨🦋 illufly © 2024</p>
    </div>
    """)

    main_ui.launch(show_api=False)