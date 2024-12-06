from fastapi import APIRouter, Depends, Query, Form, Response

from .auth import get_current_user
from ..types import MarkMeta
from ..config import get_env

def create_knowledge_endpoints(app, markmeta_dir: str=None, prefix: str="/api"):
    markmeta = MarkMeta(markmeta_dir or get_env("ILLUFLY_CHAT_LEARN"))

    @app.get(f"{prefix}/files")
    async def list_files_endpoint(user: dict = Depends(get_current_user)):
        return {
            "files": markmeta.get_files()
        }
    
    @app.get(f"{prefix}/file")
    async def get_file_endpoint(path: str = Query(...), user: dict = Depends(get_current_user)):
        try:
            with open(path, "r", encoding="utf-8") as file:
                content = file.read()
                return {
                    "path": path,
                    "content": content
                }
        except FileNotFoundError:
            return Response(status_code=404, content="文件不存在")
    
    @app.post(f"{prefix}/file")
    async def create_file_endpoint(
        path: str = Form(...), 
        content: str = Form(...),
        user: dict = Depends(get_current_user)
    ):
        try:
            markmeta.write_file(path, content)
            return {"message": "文件创建成功"}
        except Exception as e:
            return Response(status_code=500, content=str(e))
    
    @app.put(f"{prefix}/file")
    async def update_file_endpoint(
        path: str = Form(...),
        content: str = Form(...),
        user: dict = Depends(get_current_user)
    ):
        try:
            with open(path, "w", encoding="utf-8") as file:
                file.write(content)
                return {"message": "文件更新成功"}
        except FileNotFoundError:
            return Response(status_code=404, content="文件不存在")
    
    @app.delete(f"{prefix}/file")
    async def delete_file_endpoint(
        path: str = Form(...),
        user: dict = Depends(get_current_user)
    ):
        try:
            markmeta.delete_file(path)
            return {"message": "文件删除成功"}
        except FileNotFoundError:
            return Response(status_code=404, content="文件不存在")