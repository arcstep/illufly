import os
import sys

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)


from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
from fastapi.responses import StreamingResponse

import uuid
import logging

# 假设 Desk 类已经定义在 illufly.desk.base 模块中
from illufly.agent import Agent
from illufly.llm import qwen
from illufly.io.event_stream import event_stream

logging.basicConfig(level=logging.INFO)

app = FastAPI()

# 存储每一轮对话的 Desk 实例
desk_instances: Dict[str, Desk] = {}

class ChatRequest(BaseModel):
    question: str

class WriteRequest(BaseModel):
    input: Dict[str, Any]
    template: str = None
    question: str = None

class OutlineRequest(BaseModel):
    question: str = None

@app.post("/start_conversation")
async def start_conversation():
    conversation_id = str(uuid.uuid4())
    logging.info(f"Starting new conversation with ID: {conversation_id}")
    desk_instances[conversation_id] = Desk(llm=qwen)  # 假设 llm 是 None，实际使用时需要传入具体的 llm 实例
    return {"conversation_id": conversation_id}

@app.post("/achat/{conversation_id}")
async def achat(conversation_id: str, request: ChatRequest):
    if conversation_id not in desk_instances:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    logging.info(f"Processing 'achat' for conversation ID: {conversation_id} with question: {request.question}")
    desk = desk_instances[conversation_id]
    return StreamingResponse(event_stream(desk.achat(request.question)), media_type="text/event-stream")

@app.post("/awrite/{conversation_id}")
async def awrite(conversation_id: str, request: WriteRequest):
    if conversation_id not in desk_instances:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    logging.info(f"Processing 'awrite' for conversation ID: {conversation_id} with input: {request.input}")
    desk = desk_instances[conversation_id]
    return StreamingResponse(event_stream(desk.awrite(request.input, request.template, request.question)), media_type="text/event-stream")

@app.post("/afrom_outline/{conversation_id}")
async def afrom_outline(conversation_id: str, request: OutlineRequest):
    if conversation_id not in desk_instances:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    logging.info(f"Processing 'afrom_outline' for conversation ID: {conversation_id} with question: {request.question}")
    desk = desk_instances[conversation_id]
    return StreamingResponse(event_stream(desk.afrom_outline(request.question)), media_type="text/event-stream")

@app.get("/output/{conversation_id}")
async def get_output(conversation_id: str):
    if conversation_id not in desk_instances:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    logging.info(f"Getting output for conversation ID: {conversation_id}")
    desk = desk_instances[conversation_id]
    return desk.output

@app.get("/messages/{conversation_id}")
async def get_messages(conversation_id: str):
    if conversation_id not in desk_instances:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    logging.info(f"Getting messages for conversation ID: {conversation_id}")
    desk = desk_instances[conversation_id]
    return desk.messages

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)