import os
import sys
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)


from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)

from illufly.flow import Team, ReAct
from illufly.chat import ChatQwen, FakeLLM

import gradio as gr
import random
import time
import json

# ChatAgent
qwen = ChatQwen(name="qwen")

import gradio as gr
import random
import time

with gr.Blocks() as demo:
    chatbot = gr.Chatbot(type="messages")
    msg = gr.Textbox()
    clear = gr.Button("Clear")

    def user(user_message, history: list):
        return user_message, history + [{"role": "user", "content": user_message}]

    def bot(user_message, history: list):
        try:
            resp = ""
            blocks = qwen(user_message, generator="sync", verbose=True)
            for block in blocks:
                if isinstance(block, dict):
                    if block.get("data", None):
                        if block["data"].get("block_type", None) in ["text", "chunk", "tool_resp_text", "tool_resp_chunk"]:
                            resp += block["data"]["content"]
                            yield history + [{"role": "assistant", "content": resp}]
                else:
                    raise ValueError(f"Unknown block type: {type(block)}")
        except IndexError as e:
            print("Error: No content returned from qwen.", e)
            history.append({"role": "assistant", "content": "No response available."})
        return history

    msg.submit(user, [msg, chatbot], [msg, chatbot], queue=False).then(
        bot, [msg, chatbot], chatbot
    )
    clear.click(lambda: None, None, chatbot, queue=False)

demo.launch()