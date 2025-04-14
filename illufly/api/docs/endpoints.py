from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Response
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import json
import logging
from pathlib import Path

from soulseal import TokenSDK
from .file_service import FilesService, FileStatus

logger = logging.getLogger(__name__)

# 文件元数据请求模型
class FileMetadataUpdate(BaseModel):
    """文件元数据更新请求"""
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    custom_metadata: Optional[Dict[str, Any]] = None

# 文件处理请求模型
class FileProcessRequest(BaseModel):
    """文件处理请求"""
    process_type: str = Field(..., description="处理类型")
    options: Optional[Dict[str, Any]] = Field(default={}, description="处理选项")

def create_docs_endpoints(
    app, 
    token_sdk: TokenSDK,
    files_service: FilesService,
    prefix: str = "/api"
) -> List[Dict[str, Any]]:
    """创建文件管理相关的端点
    
    Args:
        app: FastAPI 应用实例
        token_sdk: 令牌SDK
        files_service: 文件服务实例
        prefix: API 前缀
        
    Returns:
        路由处理器列表
    """
    router = APIRouter(prefix=f"{prefix}", tags=["Illufly Backend - Documents"])
    
    # 获取依赖函数
    require_user = token_sdk.get_auth_dependency(logger=logger)
    
    @router.get("/files")
    async def list_files(
        include_deleted: bool = Query(False, description="是否包含已删除文件"),
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """获取用户所有文件"""
        user_id = token_claims.get('user_id')
        files = await files_service.list_files(user_id, include_deleted)
        
        # 转换为前端格式
        result = []
        for file_info in files:
            result.append({
                "id": file_info["id"],
                "original_name": file_info["original_name"],
                "size": file_info["size"],
                "type": file_info["type"],
                "extension": file_info.get("extension", ""),
                "created_at": file_info["created_at"],
                "updated_at": file_info.get("updated_at", file_info["created_at"]),
                "status": file_info.get("status", FileStatus.ACTIVE),
                "download_url": files_service.get_download_url(user_id, file_info["id"]),
                "preview_url": files_service.get_preview_url(user_id, file_info["id"]),
                # 添加其他自定义元数据
                "title": file_info.get("title", ""),
                "description": file_info.get("description", ""),
                "tags": file_info.get("tags", []),
                "custom_metadata": {k: v for k, v in file_info.items() 
                                  if k not in ["id", "original_name", "size", "type", "extension", "path", 
                                              "created_at", "updated_at", "status", "title", "description", "tags"]}
            })
        
        return result
    
    @router.post("/files/upload")
    async def upload_file(
        file: UploadFile = File(...), 
        title: Optional[str] = Form(None),
        description: Optional[str] = Form(None),
        tags: Optional[str] = Form(None),
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """上传文件"""
        user_id = token_claims.get('user_id')
        
        # 准备元数据
        metadata = {}
        if title:
            metadata["title"] = title
        if description:
            metadata["description"] = description
        if tags:
            try:
                metadata["tags"] = json.loads(tags)
            except:
                metadata["tags"] = [t.strip() for t in tags.split(',') if t.strip()]
        
        try:
            file_info = await files_service.save_file(user_id, file, metadata)
            
            return {
                "id": file_info["id"],
                "original_name": file_info["original_name"],
                "size": file_info["size"],
                "type": file_info["type"],
                "extension": file_info.get("extension", ""),
                "created_at": file_info["created_at"],
                "download_url": files_service.get_download_url(user_id, file_info["id"]),
                "preview_url": files_service.get_preview_url(user_id, file_info["id"]),
                "title": file_info.get("title", ""),
                "description": file_info.get("description", ""),
                "tags": file_info.get("tags", []),
            }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"上传文件失败: {str(e)}")
            raise HTTPException(status_code=500, detail="上传文件失败")
    
    @router.get("/files/{file_id}")
    async def get_file_info(
        file_id: str,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """获取文件信息"""
        user_id = token_claims.get('user_id')
        
        file_info = await files_service.get_file(user_id, file_id)
        if not file_info or file_info.get("status") != FileStatus.ACTIVE:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        return {
            "id": file_info["id"],
            "original_name": file_info["original_name"],
            "size": file_info["size"],
            "type": file_info["type"],
            "extension": file_info.get("extension", ""),
            "created_at": file_info["created_at"],
            "updated_at": file_info.get("updated_at", file_info["created_at"]),
            "download_url": files_service.get_download_url(user_id, file_info["id"]),
            "preview_url": files_service.get_preview_url(user_id, file_info["id"]),
            "title": file_info.get("title", ""),
            "description": file_info.get("description", ""),
            "tags": file_info.get("tags", []),
            "custom_metadata": {k: v for k, v in file_info.items() 
                               if k not in ["id", "original_name", "size", "type", "extension", "path", 
                                           "created_at", "updated_at", "status", "title", "description", "tags"]}
        }
    
    @router.patch("/files/{file_id}")
    async def update_file_metadata(
        file_id: str,
        metadata: FileMetadataUpdate,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """更新文件元数据"""
        user_id = token_claims.get('user_id')
        
        # 构建元数据字典
        update_data = {}
        
        if metadata.title is not None:
            update_data["title"] = metadata.title
            
        if metadata.description is not None:
            update_data["description"] = metadata.description
            
        if metadata.tags is not None:
            update_data["tags"] = metadata.tags
            
        if metadata.custom_metadata:
            update_data.update(metadata.custom_metadata)
        
        success = await files_service.update_metadata(user_id, file_id, update_data)
        if not success:
            raise HTTPException(status_code=404, detail="文件不存在或无法更新")
        
        # 获取更新后的文件信息
        file_info = await files_service.get_file(user_id, file_id)
        
        return {
            "id": file_info["id"],
            "original_name": file_info["original_name"],
            "size": file_info["size"],
            "type": file_info["type"],
            "extension": file_info.get("extension", ""),
            "created_at": file_info["created_at"],
            "updated_at": file_info["updated_at"],
            "download_url": files_service.get_download_url(user_id, file_info["id"]),
            "preview_url": files_service.get_preview_url(user_id, file_info["id"]),
            "title": file_info.get("title", ""),
            "description": file_info.get("description", ""),
            "tags": file_info.get("tags", []),
            "custom_metadata": {k: v for k, v in file_info.items() 
                               if k not in ["id", "original_name", "size", "type", "extension", "path", 
                                           "created_at", "updated_at", "status", "title", "description", "tags"]}
        }
    
    @router.delete("/files/{file_id}")
    async def delete_file(
        file_id: str,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """删除文件"""
        user_id = token_claims.get('user_id')
        
        success = await files_service.delete_file(user_id, file_id)
        if not success:
            raise HTTPException(status_code=404, detail="文件不存在或无法删除")
        
        return {"success": True, "message": "文件已删除"}
    
    @router.get("/files/{file_id}/download")
    async def download_file(
        file_id: str,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """下载文件"""
        user_id = token_claims.get('user_id')
        
        try:
            file_info = await files_service.get_file(user_id, file_id)
            if not file_info or file_info.get("status") != FileStatus.ACTIVE:
                raise HTTPException(status_code=404, detail="文件不存在")
            
            file_path = Path(file_info["path"])
            if not file_path.exists():
                raise HTTPException(status_code=404, detail="文件不存在")
            
            return FileResponse(
                path=file_path,
                filename=file_info["original_name"],
                media_type=files_service.get_file_mimetype(file_info["original_name"])
            )
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="文件不存在")
        except Exception as e:
            logger.error(f"下载文件失败: {str(e)}")
            raise HTTPException(status_code=500, detail="下载文件失败")
    
    @router.get("/files/{file_id}/stream")
    async def stream_file(
        file_id: str,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """流式下载文件"""
        user_id = token_claims.get('user_id')
        
        try:
            file_info = await files_service.get_file(user_id, file_id)
            if not file_info or file_info.get("status") != FileStatus.ACTIVE:
                raise HTTPException(status_code=404, detail="文件不存在")
            
            # 使用StreamingResponse来流式传输文件
            return StreamingResponse(
                content=files_service.get_file_stream(user_id, file_id),
                media_type=files_service.get_file_mimetype(file_info["original_name"]),
                headers={
                    "Content-Disposition": f'attachment; filename="{file_info["original_name"]}"'
                }
            )
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="文件不存在")
        except Exception as e:
            logger.error(f"流式下载文件失败: {str(e)}")
            raise HTTPException(status_code=500, detail="流式下载文件失败")
    
    @router.post("/files/{file_id}/process")
    async def process_file(
        file_id: str,
        process_request: FileProcessRequest,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """处理文件（切片、转换等）"""
        user_id = token_claims.get('user_id')
        
        try:
            result = await files_service.process_file(
                user_id=user_id,
                file_id=file_id,
                process_type=process_request.process_type
            )
            return result
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="文件不存在")
        except Exception as e:
            logger.error(f"处理文件失败: {str(e)}")
            raise HTTPException(status_code=500, detail=f"处理文件失败: {str(e)}")
    
    # 获取用户存储状态
    @router.get("/files/storage/status")
    async def get_storage_status(
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """获取用户存储状态"""
        user_id = token_claims.get('user_id')
        
        try:
            usage = await files_service.calculate_user_storage_usage(user_id)
            return {
                "used": usage,
                "limit": files_service.max_total_size_per_user,
                "available": files_service.max_total_size_per_user - usage,
                "usage_percentage": round(usage * 100 / files_service.max_total_size_per_user, 2)
            }
        except Exception as e:
            logger.error(f"获取存储状态失败: {str(e)}")
            raise HTTPException(status_code=500, detail="获取存储状态失败")
    
    # 添加路由到应用
    app.include_router(router)
    
    return [
        ("GET", f"{prefix}/files", list_files),
        ("POST", f"{prefix}/files/upload", upload_file),
        ("GET", f"{prefix}/files/{{file_id}}", get_file_info),
        ("PATCH", f"{prefix}/files/{{file_id}}", update_file_metadata),
        ("DELETE", f"{prefix}/files/{{file_id}}", delete_file),
        ("GET", f"{prefix}/files/{{file_id}}/download", download_file),
        ("GET", f"{prefix}/files/{{file_id}}/stream", stream_file),
        ("POST", f"{prefix}/files/{{file_id}}/process", process_file),
        ("GET", f"{prefix}/files/storage/status", get_storage_status),
    ]
