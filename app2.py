# from fastapi import FastAPI, HTTPException, Request
# from pydantic import BaseModel
# from typing import Dict, Any
# from fastapi.responses import StreamingResponse

# # 假设 Desk 类已经定义在 textlong.desk.base 模块中
from textlong.desk import Desk
from textlong.llm import qwen
# # from textlong.io.event_stream import event_stream

# import os
# import asyncio
# from dotenv import load_dotenv, find_dotenv
# load_dotenv(find_dotenv(), override=True)

# import uuid

# app = FastAPI()


# # class ChatRequest(BaseModel):
# #     question: str

# async def event_generator():
#     """
#     生成事件流数据
#     """
#     # for block in desk.chat("写一首10行的儿歌"):
#     #     print(block)
#     #     yield f"event: {block.block_type}\ndata: {block.content}\n\n"
#     yield "textlong"
#     await asyncio.sleep(1) 
#     yield "很"
#     await asyncio.sleep(1) 
#     yield "棒！"
#     await asyncio.sleep(1) 

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import asyncio
import time
import logging

logging.basicConfig(level=logging.INFO)

app = FastAPI()
desk: Desk = Desk(qwen)

async def event_generator():
    """
    生成事件流数据
    """
    for block in desk.chat("写一首10行的儿歌"):
        print(block)
        yield f"event: {block.block_type}\ndata: {block.content}\n\n"
        await asyncio.sleep(0)


@app.get("/sse")
async def sse_endpoint(request: Request):
    """
    SSE 端点
    """
    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, http="h11")