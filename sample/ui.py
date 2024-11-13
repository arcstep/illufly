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

# ChatAgent
qwen = ChatQwen(name="通义千问")
fake = FakeLLM(name="FakeLLM", sleep=0.3)
react = ReAct(planner=ChatQwen(), name="ReAct 长推理")
team = Team(agents=[qwen, fake, react], name="团队协作")

all_agents = [qwen, fake, react, team]

def escape_xml_tags(text):
    return text.replace("<", "&lt;").replace(">", "&gt;")

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
            agent_image = gr.Image(label="智能体形象")
            agent_config = gr.Textbox(label="智能体配置")

        with gr.Column(scale=3):
            toggle_button = gr.Button("...")
            chat_history = gr.Chatbot(type="messages", label="聊天记录")
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

        right_panel = gr.Column(scale=1, visible=False)
        with right_panel:
            clear = gr.Button("开始新对话")
            chat_threads = gr.Chatbot(type="messages", label="历史聊天记录")

        clear.click(lambda: None, None, chat_history, queue=False)

    visibility_state = gr.State(value=False)
    def toggle_visibility(visible):
        new_visibility = not visible
        return gr.update(visible=new_visibility), new_visibility

    toggle_button.click(
        toggle_visibility,
        inputs=visibility_state,
        outputs=[right_panel, visibility_state]
    )

    # 添加自定义 CSS 来隐藏默认的 Gradio footer
    gr.HTML("""
    <style>
        footer{display:none !important}
        body {
            font-family: Arial, sans-serif;
        }
    </style>
    <div style="text-align: center; padding: 10px; background-color: var(--background-secondary); color: var(--text-color);">
        <p>✨🦋 illufly © 2024</p>
    </div>
    """)

    main_ui.launch(show_api=False)