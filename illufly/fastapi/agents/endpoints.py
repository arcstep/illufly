from fastapi import APIRouter, Depends, HTTPException, Query, Form, status
from typing import List, Dict, Any, Optional
from sse_starlette.sse import EventSourceResponse

from ..result import Result
from ..users import TokensManager
from .agents import AgentsManager, AgentConfig

def create_agents_endpoints(
    app,
    agents_manager: AgentsManager,
    prefix: str = "/api"
):
    """Agent 相关的端点，处理 Agent 的创建、管理和调用"""

    tokens_manager = agents_manager.users_manager.tokens_manager

    @app.get(f"{prefix}/agents")
    async def list_agents(
        current_user: dict = Depends(tokens_manager.get_current_user)
    ) -> List[Dict[str, Any]]:
        """列出用户的所有 Agent"""
        user_id = current_user["user_id"]
        result = agents_manager.list_agents(user_id)
        if result.success:
            return result.to_dict()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.error)

    @app.post(f"{prefix}/agents")
    async def create_agent(
        name: str = Form(...),
        agent_type: str = Form(...),
        description: str = Form(""),
        vectordb_names: List[str] = Form([]),
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """创建新的Agent"""
        user_id = current_user["user_id"]
        result = agents_manager.create_agent(
            user_id=user_id,
            agent_type=agent_type,
            agent_name=name,
            vectordbs=vectordb_names,
        )        
        if result.success:
            return result.to_dict()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.error)

    @app.get(f"{prefix}/agents/{{agent_name}}")
    async def get_agent_info(
        agent_name: str,
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """获取 Agent 详细信息"""
        user_id = current_user["user_id"]
        result = agents_manager.list_agents(user_id)
        if result.success:
            agents = result.data
            agent_info = next(
                (agent for agent in agents if agent["agent_name"] == agent_name),
                None
            )
            if agent_info:
                return Result.ok(data=agent_info).to_dict()
            else:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.error)

    @app.post(f"{prefix}/agents/{{agent_name}}/stream")
    async def chat_with_agent(
        agent_name: str,
        prompt: str = Query(...),
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """与指定 Agent 对话"""
        user_id = current_user["user_id"]
        result = agents_manager.get_agent(user_id, agent_name)
        if result.success:
            agent = result.data
            if agent:
                return EventSourceResponse(agent(prompt, generator="async"))
            else:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.error)

    @app.patch(f"{prefix}/agents/{{agent_name}}")
    async def update_agent(
        agent_name: str,
        description: Optional[str] = Form(None),
        vectordb_names: Optional[List[str]] = Form(None),
        config: Optional[Dict[str, Any]] = Form(None),
        is_active: Optional[bool] = Form(None),
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """更新 Agent 配置"""
        user_id = current_user["user_id"]
        
        # 构建更新字典,只包含非None值
        updates = {}
        if description is not None:
            updates["description"] = description
        if vectordb_names is not None:
            updates["vectordb_names"] = vectordb_names
        if config is not None:
            updates["config"] = config
        if is_active is not None:
            updates["is_active"] = is_active
        
        result = agents_manager.update_agent_config(
            user_id, 
            agent_name, 
            updates,
        )
        if result.success:
            return result.to_dict()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.error)

    @app.delete(f"{prefix}/agents/{{agent_name}}")
    async def delete_agent(
        agent_name: str,
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """删除 Agent"""
        user_id = current_user["user_id"]
        result = agents_manager.remove_agent(user_id, agent_name)
        if result.success:
            return result.to_dict()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.error)

    # 新增知识库相关端点
    @app.get(f"{prefix}/vectordbs")
    async def list_vectordbs(
        current_user: dict = Depends(tokens_manager.get_current_user)
    ) -> List[str]:
        """列出用户的所有知识库"""
        user_id = current_user["user_id"]
        result = agents_manager.vectordb_manager.list_dbs(user_id)
        if result.success:
            return result.data
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.message)

    @app.post(f"{prefix}/vectordbs")
    async def create_vectordb(
        name: str = Form(...),
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """创建新的知识库"""
        user_id = current_user["user_id"]
        result = agents_manager.vectordb_manager.create_db(
            user_id=user_id,
            db_name=name
        )
        if result.success:
            return result.to_dict()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.error)


    # 知识库管理端点
    @app.get(f"{prefix}/vectordbs/{{db_name}}")
    async def get_vectordb_info(
        db_name: str,
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """获取知识库详细信息"""
        user_id = current_user["user_id"]
        result = agents_manager.vectordb_manager.get_db(user_id, db_name)
        if result.success:
            return result.to_dict()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.error)

    @app.delete(f"{prefix}/vectordbs/{{db_name}}")
    async def delete_vectordb(
        db_name: str,
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """删除知识库"""
        user_id = current_user["user_id"]
        result = agents_manager.vectordb_manager.remove_db(user_id, db_name)
        if result.success:
            return result.to_dict()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.error)

    @app.patch(f"{prefix}/vectordbs/{{db_name}}")
    async def update_vectordb(
        db_name: str,
        db_type: Optional[str] = Form(None),
        top_k: Optional[int] = Form(None),
        config: Optional[Dict[str, Any]] = Form(None),
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """更新知识库配置"""
        user_id = current_user["user_id"]
        
        # 构建更新字典，只包含非None值
        updates = {}
        if db_type is not None:
            updates["db_type"] = db_type
        if top_k is not None:
            updates["top_k"] = top_k
        if config is not None:
            updates["config"] = config
            
        result = agents_manager.vectordb_manager.update_db_config(user_id, db_name, updates)
        if result.success:
            return result.to_dict()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.error)

    # 知识库管理端点
    @app.get(f"{prefix}/vectordbs/{{db_name}}/knowledge")
    async def list_knowledge(
        db_name: str,
        page: int = Query(1, ge=1),
        page_size: int = Query(10, ge=1, le=100),
        sort_by: str = Query("id", regex="^(id|summary|source|tags)$"),
        reverse: bool = Query(False),
        tags: Optional[List[str]] = Query(None),
        match_all_tags: bool = Query(True),
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """获取知识列表"""
        user_id = current_user["user_id"]
        result = agents_manager.vectordb_manager.get_db(user_id, db_name)
        if result.success:
            db = result.data
            resp = db.knowledge.get_meta_list(
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                reverse=reverse,
                tags=tags,
                match_all_tags=match_all_tags
            )
            return Result.ok(data=resp).to_dict()
        raise HTTPException(status_code=404, detail=result.error)

    @app.get(f"{prefix}/vectordbs/{{db_name}}/knowledge/{{knowledge_id}}")
    async def get_knowledge(
        knowledge_id: str,
        db_name: str,
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """获取知识详情"""
        user_id = current_user["user_id"]
        result = agents_manager.vectordb_manager.get_db(user_id, db_name)
        if result.success:
            db = result.data
            if not db:
                raise HTTPException(status_code=404, detail="Knowledge base not found")
            content = db.knowledge.get(knowledge_id)
            return Result.ok(data={
                "id": knowledge_id,
                "content": content
            }).to_dict()
        raise HTTPException(status_code=404, detail=result.error)

    @app.post(f"{prefix}/vectordbs/{{db_name}}/knowledge")
    async def create_knowledge(
        db_name: str,
        content: str = Form(...),
        tags: Optional[List[str]] = Form(None),
        summary: Optional[str] = Form(""),
        source: Optional[str] = Form(None),
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """创建新知识"""
        user_id = current_user["user_id"]
        result = agents_manager.vectordb_manager.get_db(user_id, db_name)
        if result.success:
            db = result.data
            if not db:
                raise HTTPException(status_code=404, detail="Knowledge base not found")
            knowledge_id = db.add(
                text=content,
                tags=tags,
                summary=summary,
                source=source
            )
            return Result.ok(data={
                "message": "知识创建成功",
                "id": knowledge_id
            }).to_dict()
        raise HTTPException(status_code=500, detail=result.error)

    @app.put(f"{prefix}/vectordbs/{{db_name}}/knowledge/{{knowledge_id}}")
    async def update_knowledge(
        knowledge_id: str,
        db_name: str,
        content: Optional[str] = Form(None),
        tags: Optional[str] = Form(None),
        summary: Optional[str] = Form(None),
        source: Optional[str] = Form(None),
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """更新知识"""
        user_id = current_user["user_id"]
        result = agents_manager.vectordb_manager.get_db(user_id, db_name)
        if result.success:
            db = result.data
            if not db:
                raise HTTPException(status_code=404, detail="Knowledge base not found")
            tags_list = tags.split(',') if tags else None
            success = db.knowledge.update(
                knowledge_id=knowledge_id,
                text=content,
                tags=tags_list,
                summary=summary,
                source=source
            )
            if success:
                return Result.ok(data={"message": "知识更新成功"}).to_dict()
            raise HTTPException(status_code=400, detail="更新失败，可能存在重复内容")
        raise HTTPException(status_code=404, detail=result.error)

    @app.delete(f"{prefix}/vectordbs/{{db_name}}/knowledge/{{knowledge_id}}")
    async def delete_knowledge(
        knowledge_id: str,
        db_name: str,
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """删除知识"""
        user_id = current_user["user_id"]
        result = agents_manager.vectordb_manager.get_db(user_id, db_name)
        if result.success:
            db = result.data
            if not db:
                raise HTTPException(status_code=404, detail="Knowledge base not found")
            db.knowledge.delete(knowledge_id)
            return Result.ok(data={"message": "知识删除成功"}).to_dict()
        raise HTTPException(status_code=404, detail=result.error)

    # 知识库搜索
    @app.get(f"{prefix}/vectordbs/{{db_name}}/knowledge/search")
    async def search_knowledge(
        db_name: str,
        query: str = Query(..., description="搜索查询"),
        limit: int = Query(10, ge=1, le=100),
        current_user: dict = Depends(tokens_manager.get_current_user)
    ):
        """搜索知识"""
        user_id = current_user["user_id"]
        result = agents_manager.vectordb_manager.get_db(user_id, db_name)
        if result.success:
            db = result.data
            if not db:
                raise HTTPException(status_code=404, detail="Knowledge base not found")
            results = db.search(query, limit=limit)
            return Result.ok(data={
                "query": query,
                "results": results
            }).to_dict()
        raise HTTPException(status_code=500, detail=result.error)

    return {
        "list_agents": list_agents,
        "create_agent": create_agent,
        "get_agent_info": get_agent_info,
        "delete_agent": delete_agent,
        "update_agent": update_agent,
        "chat_with_agent": chat_with_agent,
        ##
        "list_vectordbs": list_vectordbs,
        "create_vectordb": create_vectordb,
        "get_vectordb_info": get_vectordb_info,
        "delete_vectordb": delete_vectordb,
        "update_vectordb": update_vectordb,
        ##
        "list_knowledge": list_knowledge,
        "create_knowledge": create_knowledge,
        "get_knowledge": get_knowledge,
        "delete_knowledge": delete_knowledge,
        "update_knowledge": update_knowledge,
        "search_knowledge": search_knowledge,
    }
