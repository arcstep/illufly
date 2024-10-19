import os
import sys
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, project_root)
print("path: ", project_root)

import time
import gradio as gr
from illufly.chat import ChatQwen

qwen = ChatQwen()

def ask_qwen(message, history, system_prompt):
    output = ""
    for b in qwen.call(message):
        if b.block_type == "chunk":
            output += b.text
            yield output

gr.ChatInterface(
    ask_qwen,
    type="messages",
    additional_inputs=[
        gr.Textbox(
            label="System Prompt",
            value="You are a helpful assistant",
            placeholder="Enter a system prompt for the assistant",
        )
    ],
    title="Chat with Qwen",
    description="Ask Qwen anything",
    theme="soft",
    # examples=[
    #     "Hello",
    #     "Am I cool?",
    #     "Are tomatoes vegetables?"
    # ],
    cache_examples=True,
).launch()
