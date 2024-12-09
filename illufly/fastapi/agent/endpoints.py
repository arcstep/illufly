from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Dict, Any
from sse_starlette.sse import EventSourceResponse
from ..auth import get_current_user

def create_agent_endpoints(app, user_manager: "UserManager", prefix: str="/api"):
    """Agent 相关的端点，处理 Agent 的创建、管理和调用"""

    @app.get(f"{prefix}/agents")
    async def list_agents(
        current_user: dict = Depends(get_current_user)
    ) -> List[Dict[str, Any]]:
        """列出用户的所有 Agent"""
        username = current_user["username"]
        context = user_manager.get_user_context(username)
        if not context:
            raise HTTPException(status_code=404, detail="User context not found")
            
        return [
            {
                "name": agent.name,
                "type": agent.type,
                "description": agent.description,
                "created_at": agent.created_at.isoformat(),
                "last_used": agent.last_used.isoformat(),
                "is_active": agent.is_active
            }
            for agent in context.list_agents()
        ]

    @app.post(f"{prefix}/agents")
    async def create_agent(
        agent_data: dict,
        current_user: dict = Depends(get_current_user)
    ):
        """创建新的 Agent"""
        username = current_user["username"]
        success = user_manager.create_agent(
            username=username,
            agent_type=agent_data["type"],
            agent_name=agent_data["name"],
            vectordbs=agent_data.get("vectordbs", []),
            description=agent_data.get("description", "")
        )
        
        if success:
            return {"message": f"Agent {agent_data['name']} created successfully"}
        raise HTTPException(status_code=400, detail="Failed to create agent")

    @app.get(f"{prefix}/agents/{{agent_name}}")
    async def get_agent_info(
        agent_name: str,
        current_user: dict = Depends(get_current_user)
    ):
        """获取 Agent 详细信息"""
        username = current_user["username"]
        agent_info = user_manager.get_agent_info(username, agent_name)
        if not agent_info:
            raise HTTPException(status_code=404, detail="Agent not found")
            
        return {
            "name": agent_info.name,
            "type": agent_info.type,
            "description": agent_info.description,
            "created_at": agent_info.created_at.isoformat(),
            "last_used": agent_info.last_used.isoformat(),
            "is_active": agent_info.is_active,
            "events_history_path": agent_info.events_history_path,
            "memory_history_path": agent_info.memory_history_path,
            "vectordbs": [str(db) for db in agent_info.vectordbs]
        }

    @app.post(f"{prefix}/agents/{{agent_name}}/chat")
    async def chat_with_agent(
        agent_name: str,
        prompt: str = Query(...),
        current_user: dict = Depends(get_current_user)
    ):
        """与指定 Agent 对话"""
        username = current_user["username"]
        agent = user_manager.get_agent(username, agent_name)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
            
        return EventSourceResponse(agent(prompt, generator="async"))

    @app.patch(f"{prefix}/agents/{{agent_name}}")
    async def update_agent(
        agent_name: str,
        updates: Dict[str, Any],
        current_user: dict = Depends(get_current_user)
    ):
        """更新 Agent 配置"""
        username = current_user["username"]
        if user_manager.update_agent(username, agent_name, updates):
            return {"message": f"Agent {agent_name} updated successfully"}
        raise HTTPException(status_code=404, detail="Agent not found")

    @app.delete(f"{prefix}/agents/{{agent_name}}")
    async def delete_agent(
        agent_name: str,
        current_user: dict = Depends(get_current_user)
    ):
        """删除 Agent"""
        username = current_user["username"]
        if user_manager.delete_agent(username, agent_name):
            return {"message": f"Agent {agent_name} deleted successfully"}
        raise HTTPException(status_code=404, detail="Agent not found")