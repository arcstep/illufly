import os
import sys
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)


from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)

from illufly.flow import Team, ReAct
from illufly.chat import ChatQwen

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()

# ChatAgent
chat = ChatQwen(name="qwen")
@app.get("/chat")
async def chat_endpoint(prompt: str):
    return StreamingResponse(
        chat(prompt, generator="async"),
        media_type="text/plain"
    )

# ReAct
naming = ChatQwen(name="naming", description="我是一个命名专家，根据问题生成一个名字")
react = ReAct(ChatQwen(tools=[naming]), name="react")
@app.get("/react")
async def react_endpoint(prompt: str):
    return StreamingResponse(
        react(prompt, generator="async"),
        media_type="text/plain"
    )

# Team
team = Team(name="if1")
team.hire(
    ChatQwen(name="qwen"),
    ChatQwen(name="小说家", memory=(('system', '你是一个小说家，根据我的问题生成一句话小说')))
)

@app.get("/team")
async def team_endpoint(prompt: str):
    return StreamingResponse(
        team(prompt, generator="async"),
        media_type="text/plain"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, http="h11")

