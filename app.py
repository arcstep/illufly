from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List
import uuid
import asyncio

# 假设 Desk 类已经定义在 textlong.desk.base 模块中
from textlong.desk import Desk
from textlong.llm import qwen

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
    desk_instances[conversation_id] = Desk(llm=qwen)  # 假设 llm 是 None，实际使用时需要传入具体的 llm 实例
    return {"conversation_id": conversation_id}

@app.post("/achat/{conversation_id}")
async def achat(conversation_id: str, request: ChatRequest):
    if conversation_id not in desk_instances:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    desk = desk_instances[conversation_id]
    response = []
    async for block in desk.achat(request.question):
        response.append(block)
    return response

@app.post("/awrite/{conversation_id}")
async def awrite(conversation_id: str, request: WriteRequest):
    if conversation_id not in desk_instances:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    desk = desk_instances[conversation_id]
    response = []
    async for block in desk.awrite(request.input, template=request.template, question=request.question):
        response.append(block)
    return response

@app.post("/afrom_outline/{conversation_id}")
async def afrom_outline(conversation_id: str, request: OutlineRequest):
    if conversation_id not in desk_instances:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    desk = desk_instances[conversation_id]
    response = []
    async for block in desk.afrom_outline(question=request.question):
        response.append(block)
    return response

@app.get("/output/{conversation_id}")
async def get_output(conversation_id: str):
    if conversation_id not in desk_instances:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    desk = desk_instances[conversation_id]
    return desk.output

@app.get("/messages/{conversation_id}")
async def get_messages(conversation_id: str):
    if conversation_id not in desk_instances:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    desk = desk_instances[conversation_id]
    return desk.messages

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)