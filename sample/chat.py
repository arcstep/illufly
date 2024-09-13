import os
import sys

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from illufly.agent import Agent
from illufly.llm import zhipu

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import asyncio
import time
import logging

logging.basicConfig(level=logging.INFO)

app = FastAPI()
agent: Agent = Agent(zhipu)

async def event_generator():
    """
    生成事件流数据
    """
    for block in agent.chat("写一首10行的儿歌"):
        print(block)
        yield f"event: {block.block_type}\ndata: {block.content}\n\n"
        await asyncio.sleep(0)


@app.post("/sse")
async def sse_endpoint(request: Request):
    """
    SSE 端点
    """
    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, http="h11")