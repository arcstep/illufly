from fastapi import APIRouter, Depends, Query, Form
from sse_starlette.sse import EventSourceResponse

from .auth import get_current_user

def create_agent_endpoints(app, agent, prefix: str="/api"):
    @app.get(f"{prefix}")
    async def agent_endpoint(prompt: str = Query(...), user: dict = Depends(get_current_user)):
        return EventSourceResponse(agent(prompt, generator="async"))

    @app.post(f"{prefix}/history/change")
    async def agent_history_change_endpoint(history_id: str = Form(...), user: dict = Depends(get_current_user)):
        _, history = agent.events_history.load_events_history(history_id)
        return {
            "history_id": history_id,
            "history": history.get("callings", {})
        }

    @app.get(f"{prefix}/history/list")
    async def agent_history_list_endpoint(user: dict = Depends(get_current_user)):
        return {
            "history_id": agent.events_history.events_history_id,
            "history_list": list(reversed(agent.events_history.list_events_histories()))
        }

    @app.post(f"{prefix}/history/new")
    async def agent_history_new_endpoint(user: dict = Depends(get_current_user)):
        agent.clear()
        return agent.events_history.create_new_history()