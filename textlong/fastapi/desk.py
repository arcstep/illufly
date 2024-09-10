from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, Request
from datetime import datetime, timedelta
from typing import Dict

from ..llm import fake_llm, zhipu, qwen, openai

from .auth import verify_jwt, get_current_user
from ..config import get_env
from ..desk import Desk

async def _config_modifier(config: Dict, request: Request) -> Dict:
    """Modify the config for each request."""
    payload = verify_jwt(request.headers.get("Authorization"))
    print(payload)
    # config["configurable"] = {"username": payload}
    # config["configurable"]["user_id"] = user.username
    return config

def create_desk_api(llm: Runnable):
    router = APIRouter()
    
    # 创作
    add_routes(
        router,
        create_chain(llm),
        per_req_config_modifier=_config_modifier,
        dependencies=[Depends(get_current_user)],
        enabled_endpoints=["invoke", "stream"],
        path = "/writing"
    )

    @router.post("/chat")
    async def _init_project(project_id: str, user: dict = Depends(get_current_user)):
        """
        初始化新的写作项目。
        """
        return init_project(project_id=project_id)

    @router.get("/project/{project_id}")
    async def _list_resource(project_id: str, user: dict = Depends(get_current_user)):
        """
        列举项目内所有 Markdown 资源文件。
        """
        p = Project(llm, project_id)
        return p.list_resource()

    @router.get("/project/{project_id}/{resource_id}")
    async def _read_resource(
        project_id: str,
        resource_id: str,
        user: dict = Depends(get_current_user)
    ):
        """
        读取项目内指定 Markdown 资源文件。
        """
        p = Project(llm, project_id)
        return p.load_markdown(resource_id)

    @router.post("/project/{project_id}/save_as")
    async def _save_as(
        project_id: str,
        res_name: str,
        txt: str="",
        current_user: dict = Depends(get_current_user)
    ):
        """
        将文本保存到项目内指定 Markdown 文件。
        """
        p = Project(llm, project_id)
        return p.save_markdown_as(res_name, txt)
    
    return router


