from fastapi import APIRouter, Depends, HTTPException, Query, Form
from typing import List, Dict, Any, Optional
from sse_starlette.sse import EventSourceResponse
from ..auth import get_current_user
from .manager import AgentManager

def create_agent_endpoints(
    app, 
    agent_manager: AgentManager,
    prefix: str = "/api"
):
    """Agent 相关的端点，处理 Agent 的创建、管理和调用"""

    @app.get(f"{prefix}/agents")
    async def list_agents(
        current_user: dict = Depends(get_current_user)
    ) -> List[Dict[str, Any]]:
        """列出用户的所有 Agent"""
        username = current_user["username"]
        return agent_manager.list_agents(username, requester=username)

    @app.post(f"{prefix}/agents")
    async def create_agent(
        agent_data: dict,
        current_user: dict = Depends(get_current_user)
    ):
        """创建新的 Agent"""
        username = current_user["username"]
        success = agent_manager.create_agent(
            username=username,
            agent_type=agent_data["type"],
            agent_name=agent_data["name"],
            vectordb_names=agent_data.get("vectordbs", []),
            requester=username,
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
        agents = agent_manager.list_agents(username, requester=username)
        agent_info = next(
            (agent for agent in agents if agent["name"] == agent_name),
            None
        )
        
        if not agent_info:
            raise HTTPException(status_code=404, detail="Agent not found")
            
        return agent_info

    @app.post(f"{prefix}/agents/{{agent_name}}/chat")
    async def chat_with_agent(
        agent_name: str,
        prompt: str = Query(...),
        current_user: dict = Depends(get_current_user)
    ):
        """与指定 Agent 对话"""
        username = current_user["username"]
        agent = agent_manager.get_agent(username, agent_name, requester=username)
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
        if agent_manager.update_agent_config(
            username, 
            agent_name, 
            updates,
            requester=username
        ):
            return {"message": f"Agent {agent_name} updated successfully"}
        raise HTTPException(status_code=404, detail="Agent not found")

    @app.delete(f"{prefix}/agents/{{agent_name}}")
    async def delete_agent(
        agent_name: str,
        current_user: dict = Depends(get_current_user)
    ):
        """删除 Agent"""
        username = current_user["username"]
        if agent_manager.remove_agent(username, agent_name, requester=username):
            return {"message": f"Agent {agent_name} deleted successfully"}
        raise HTTPException(status_code=404, detail="Agent not found")

    # 新增知识库相关端点
    @app.get(f"{prefix}/vectordbs")
    async def list_vectordbs(
        current_user: dict = Depends(get_current_user)
    ) -> List[str]:
        """列出用户的所有知识库"""
        username = current_user["username"]
        return agent_manager.list_dbs(username, requester=username)

    @app.post(f"{prefix}/vectordbs")
    async def create_vectordb(
        db_data: dict,
        current_user: dict = Depends(get_current_user)
    ):
        """创建新的知识库"""
        username = current_user["username"]
        success = agent_manager.create_db(
            username=username,
            db_name=db_data["name"],
            requester=username
        )
        
        if success:
            return {"message": f"VectorDB {db_data['name']} created successfully"}
        raise HTTPException(status_code=400, detail="Failed to create vectordb")

    # 知识库管理端点
    @app.get(f"{prefix}/knowledge")
    async def list_knowledge(
        db_name: str = Query(..., description="知识库名称"),
        page: int = Query(1, ge=1),
        page_size: int = Query(10, ge=1, le=100),
        sort_by: str = Query("id", regex="^(id|summary|source|tags)$"),
        reverse: bool = Query(False),
        tags: Optional[List[str]] = Query(None),
        match_all_tags: bool = Query(True),
        current_user: dict = Depends(get_current_user)
    ):
        """获取知识列表"""
        username = current_user["username"]
        db = agent_manager.get_db(username, db_name, requester=username)
        if not db:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
            
        return db.knowledge.get_meta_list(
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            reverse=reverse,
            tags=tags,
            match_all_tags=match_all_tags
        )

    @app.get(f"{prefix}/knowledge/{{knowledge_id}}")
    async def get_knowledge(
        knowledge_id: str,
        db_name: str = Query(..., description="知识库名称"),
        current_user: dict = Depends(get_current_user)
    ):
        """获取知识详情"""
        username = current_user["username"]
        db = agent_manager.get_db(username, db_name, requester=username)
        if not db:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
            
        try:
            content = db.knowledge.get(knowledge_id)
            return {
                "id": knowledge_id,
                "content": content
            }
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Knowledge not found")

    @app.post(f"{prefix}/knowledge")
    async def create_knowledge(
        db_name: str = Query(..., description="知识库名称"),
        content: str = Form(...),
        tags: Optional[List[str]] = Form(None),
        summary: Optional[str] = Form(""),
        source: Optional[str] = Form(None),
        current_user: dict = Depends(get_current_user)
    ):
        """创建新知识"""
        username = current_user["username"]
        db = agent_manager.get_db(username, db_name, requester=username)
        if not db:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
            
        try:
            knowledge_id = db.add(
                text=content,
                tags=tags,
                summary=summary,
                source=source
            )
            return {
                "message": "知识创建成功",
                "id": knowledge_id
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.put(f"{prefix}/knowledge/{{knowledge_id}}")
    async def update_knowledge(
        knowledge_id: str,
        db_name: str = Query(..., description="知识库名称"),
        content: Optional[str] = Form(None),
        tags: Optional[str] = Form(None),
        summary: Optional[str] = Form(None),
        source: Optional[str] = Form(None),
        current_user: dict = Depends(get_current_user)
    ):
        """更新知识"""
        username = current_user["username"]
        db = agent_manager.get_db(username, db_name, requester=username)
        if not db:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
            
        try:
            tags_list = tags.split(',') if tags else None
            success = db.knowledge.update(
                knowledge_id=knowledge_id,
                text=content,
                tags=tags_list,
                summary=summary,
                source=source
            )
            if success:
                return {"message": "知识更新成功"}
            raise HTTPException(status_code=400, detail="更新失败，可能存在重复内容")
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="知识不存在")

    @app.delete(f"{prefix}/knowledge/{{knowledge_id}}")
    async def delete_knowledge(
        knowledge_id: str,
        db_name: str = Query(..., description="知识库名称"),
        current_user: dict = Depends(get_current_user)
    ):
        """删除知识"""
        username = current_user["username"]
        db = agent_manager.get_db(username, db_name, requester=username)
        if not db:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
            
        try:
            db.knowledge.delete(knowledge_id)
            return {"message": "知识删除成功"}
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="知识不存在")

    # 知识库搜索端点
    @app.get(f"{prefix}/knowledge/search")
    async def search_knowledge(
        query: str = Query(..., description="搜索查询"),
        db_name: str = Query(..., description="知识库名称"),
        limit: int = Query(10, ge=1, le=100),
        current_user: dict = Depends(get_current_user)
    ):
        """搜索知识"""
        username = current_user["username"]
        db = agent_manager.get_db(username, db_name, requester=username)
        if not db:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
            
        try:
            results = db.search(query, limit=limit)
            return {
                "query": query,
                "results": results
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))