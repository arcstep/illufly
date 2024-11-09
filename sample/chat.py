import os
import sys

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from illufly.flow import Team
from illufly.chat import ChatQwen

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import asyncio
import time
import logging

logging.basicConfig(level=logging.INFO)

app = FastAPI()

team = Team(name="if1")
team.hire(
    ChatQwen(name="qwen"),
    ChatQwen(name="小说家", memory=(('system', '你是一个小说家，根据我的问题生成一句话小说')))
)

@app.get("/example")
async def example_endpoint(prompt: str):
    # 假设 team 是一个返回异步生成器的函数
    async def async_generator():
        async for block in team(prompt, generator="async"):
            yield block

    return StreamingResponse(async_generator(), media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, http="h11")

