"""
Knowledge Module Endpoints

This module defines the knowledge-related API endpoints.
"""

from fastapi import Depends, HTTPException, status, Query, Form, Response
from typing import List, Optional
from datetime import datetime
from ..auth.dependencies import get_current_user, require_roles
from ..user.models import UserRole
from .manager import KnowledgeManager

def create_knowledge_endpoints(app, knowledge_manager: KnowledgeManager, prefix: str = "/api"):
    """创建知识库相关的端点"""

    # 知识库管理端点
    @app.get(f"{prefix}/knowledge/bases")
    async def list_knowledge_bases(
        current_user: dict = Depends(require_roles(UserRole.USER))
    ):
        """列出用户可访问的知识库"""
        bases = knowledge_manager.list_dbs(owner=current_user["username"])
        return [base.to_dict() for base in bases]

    @app.get(f"{prefix}/knowledge/bases/{{name}}")
    async def get_knowledge_base(
        name: str,
        current_user: dict = Depends(require_roles(UserRole.USER))
    ):
        """获取知识库详情"""
        base = knowledge_manager.get_base_info(
            owner=current_user["username"],
            name=name
        )
        if not base:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge base not found"
            )
        return base.to_dict()

    # 知识条目管理端点
    @app.get(f"{prefix}/knowledge/bases/{{base_name}}/entries")
    async def list_knowledge_entries(
        base_name: str,
        page: int = Query(1, ge=1),
        page_size: int = Query(10, ge=1, le=100),
        sort_by: str = Query("id", regex="^(id|summary|source|tags)$"),
        reverse: bool = Query(False),
        tags: Optional[List[str]] = Query(None),
        match_all_tags: bool = Query(True),
        current_user: dict = Depends(require_roles(UserRole.USER))
    ):
        """获取知识条目列表"""
        db = knowledge_manager.get_db_by_owner(
            owner=current_user["username"],
            name=base_name
        )
        if not db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge base not found"
            )
        
        return db.knowledge.get_meta_list(
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            reverse=reverse,
            tags=tags,
            match_all_tags=match_all_tags
        )

    @app.get(f"{prefix}/knowledge/bases/{{base_name}}/entries/{{entry_id}}")
    async def get_knowledge_entry(
        base_name: str,
        entry_id: str,
        current_user: dict = Depends(require_roles(UserRole.USER))
    ):
        """获取知识条目详情"""
        db = knowledge_manager.get_db_by_owner(
            owner=current_user["username"],
            name=base_name
        )
        if not db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge base not found"
            )

        try:
            content = db.knowledge.get(entry_id)
            meta = db.knowledge.get_meta(entry_id)
            return {
                "id": entry_id,
                "content": content,
                **meta
            }
        except FileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge entry not found"
            )

    @app.post(f"{prefix}/knowledge/bases/{{base_name}}/entries")
    async def create_knowledge_entry(
        base_name: str,
        content: str = Form(...),
        tags: Optional[List[str]] = Form(None),
        summary: Optional[str] = Form(""),
        source: Optional[str] = Form(None),
        current_user: dict = Depends(require_roles(UserRole.USER))
    ):
        """创建新的知识条目"""
        db = knowledge_manager.get_db_by_owner(
            owner=current_user["username"],
            name=base_name
        )
        if not db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge base not found"
            )

        try:
            entry_id = db.add(
                text=content,
                tags=tags,
                summary=summary,
                source=source
            )
            return {
                "message": "Knowledge entry created successfully",
                "id": entry_id
            }
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )

    @app.put(f"{prefix}/knowledge/bases/{{base_name}}/entries/{{entry_id}}")
    async def update_knowledge_entry(
        base_name: str,
        entry_id: str,
        content: Optional[str] = Form(None),
        tags: Optional[str] = Form(None),
        summary: Optional[str] = Form(None),
        source: Optional[str] = Form(None),
        current_user: dict = Depends(require_roles(UserRole.USER))
    ):
        """更新知识条目"""
        db = knowledge_manager.get_db_by_owner(
            owner=current_user["username"],
            name=base_name
        )
        if not db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge base not found"
            )

        try:
            tags_list = tags.split(',') if tags else None
            success = db.knowledge.update(
                knowledge_id=entry_id,
                text=content,
                tags=tags_list,
                summary=summary,
                source=source
            )
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Update failed, possibly due to duplicate content"
                )
            return {"message": "Knowledge entry updated successfully"}
        except FileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge entry not found"
            )

    @app.delete(f"{prefix}/knowledge/bases/{{base_name}}/entries/{{entry_id}}")
    async def delete_knowledge_entry(
        base_name: str,
        entry_id: str,
        current_user: dict = Depends(require_roles(UserRole.USER))
    ):
        """删除知识条目"""
        db = knowledge_manager.get_db_by_owner(
            owner=current_user["username"],
            name=base_name
        )
        if not db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge base not found"
            )

        try:
            db.knowledge.delete(entry_id)
            return {"message": "Knowledge entry deleted successfully"}
        except FileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge entry not found"
            )