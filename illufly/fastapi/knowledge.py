from fastapi import APIRouter, Depends, Query, Form, Response
from typing import List, Optional

from .auth import get_current_user
from ..rag import FaissDB
from ..config import get_env
from ..types import VectorDB

def create_knowledge_endpoints(app, db: VectorDB=None, prefix: str="/api"):
    knowledge = db.knowledge

    @app.get(f"{prefix}/knowledge")
    async def list_knowledge_endpoint(
        page: int = Query(1, ge=1),
        page_size: int = Query(10, ge=1, le=100),
        sort_by: str = Query("id", regex="^(id|summary|source|tags)$"),
        reverse: bool = Query(False),
        tags: Optional[List[str]] = Query(None),
        match_all_tags: bool = Query(True),
        user: dict = Depends(get_current_user)
    ):
        """获取知识列表"""
        return knowledge.get_meta_list(
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            reverse=reverse,
            tags=tags,
            match_all_tags=match_all_tags
        )
    
    @app.get(f"{prefix}/knowledge/{{knowledge_id}}")
    async def get_knowledge_endpoint(
        knowledge_id: str,
        user: dict = Depends(get_current_user)
    ):
        """获取知识详情"""
        try:
            content = knowledge.get(knowledge_id)
            return {
                "id": knowledge_id,
                "content": content
            }
        except FileNotFoundError:
            return Response(status_code=404, content="知识不存在")
    
    @app.post(f"{prefix}/knowledge")
    async def create_knowledge_endpoint(
        content: str = Form(...),
        tags: Optional[List[str]] = Form(None),
        summary: Optional[str] = Form(""),
        source: Optional[str] = Form(None),
        user: dict = Depends(get_current_user)
    ):
        """创建新知识"""
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
            return Response(status_code=500, content=str(e))
    
    @app.put(f"{prefix}/knowledge/{{knowledge_id}}")
    async def update_knowledge_endpoint(
        knowledge_id: str,
        content: Optional[str] = Form(None),
        tags: Optional[List[str]] = Form(None),
        summary: Optional[str] = Form(None),
        source: Optional[str] = Form(None),
        user: dict = Depends(get_current_user)
    ):
        """更新知识"""
        try:
            success = knowledge.update(
                knowledge_id=knowledge_id,
                text=content,
                tags=tags,
                summary=summary,
                source=source
            )
            if success:
                return {"message": "知识更新成功"}
            return Response(status_code=400, content="更新失败，可能存在重复内容")
        except FileNotFoundError:
            return Response(status_code=404, content="知识不存在")
    
    @app.delete(f"{prefix}/knowledge/{{knowledge_id}}")
    async def delete_knowledge_endpoint(
        knowledge_id: str,
        user: dict = Depends(get_current_user)
    ):
        """删除知识"""
        try:
            knowledge.delete(knowledge_id)
            return {"message": "知识删除成功"}
        except FileNotFoundError:
            return Response(status_code=404, content="知识不存在")