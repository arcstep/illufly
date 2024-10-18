import os
import sys

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, project_root)
print("path: ", project_root)

import time
import gradio as gr
from typing import Union, List
from illufly.types import Runnable


class MyRun(Runnable):
    def call(*args, **kwargs):
        yield "hi\n"
        yield "illufly!\n"

def greet(prompt):
    time.sleep(1)
    yield "hi\n"
    time.sleep(1)
    yield "illufly!\n"

demo = gr.Interface(
    fn=greet,
    inputs=["text"],
    outputs=["text"],
    stream=True,
)

demo.launch()
