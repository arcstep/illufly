from fastapi import FastAPI, Depends, HTTPException, File, Form, UploadFile, Request
from fastapi.responses import FileResponse
from typing import Dict, Any, List, Optional, Callable, Tuple
from pydantic import BaseModel, HttpUrl
from enum import Enum
import logging
import os
import time
import json
from pathlib import Path

from soulseal import TokenSDK
from ..schemas import Result, HttpMethod
from ..http import handle_errors
from ...documents.base import DocumentService, DocumentStatus, ProcessStage

# 文档元数据更新请求模型
class DocumentMetadataUpdate(BaseModel):
    """文档元数据更新请求"""
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    extra_fields: Optional[Dict[str, Any]] = None

# 远程URL书签请求模型
class BookmarkUrlRequest(BaseModel):
    """远程URL书签请求"""
    url: HttpUrl
    filename: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None

def create_documents_endpoints(
    app: FastAPI,
    token_sdk: TokenSDK,
    documents_service: DocumentService,
    prefix: str = "/api",
    logger: logging.Logger = None
) -> List[Tuple[HttpMethod, str, Callable]]:
    """创建文档管理相关的API端点
    
    Args:
        app: FastAPI应用实例
        token_sdk: 令牌SDK
        documents_service: 文档服务
        prefix: API前缀
        logger: 日志记录器
    
    Returns:
        List[Tuple[HttpMethod, str, Callable]]: 
            元组列表 (HTTP方法, 路由路径, 处理函数)
    """
    logger = logger or logging.getLogger(__name__)
    require_user = token_sdk.get_auth_dependency(logger=logger)

    @handle_errors()
    async def list_documents(
        request: Request,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """获取用户所有文档"""
        user_id = token_claims["user_id"]
        documents = await documents_service.list_documents(user_id)
        
        # 转换为前端格式
        result = []
        for doc_info in documents:
            # 确定下载URL - 仅本地文件可下载原始内容
            download_url = None
            if doc_info.get("source_type") == "local":
                download_url = f"{prefix}/documents/{doc_info['document_id']}/download"
            
            # 使用扁平化结构
            result.append({
                "document_id": doc_info["document_id"],
                "original_name": doc_info["original_name"],
                "size": doc_info.get("size", 0),
                "type": doc_info.get("type", ""),
                "extension": doc_info.get("extension", ""),
                "created_at": doc_info["created_at"],
                "updated_at": doc_info.get("updated_at", doc_info["created_at"]),
                "status": doc_info.get("status", DocumentStatus.ACTIVE),
                "download_url": download_url,
                "title": doc_info.get("title", ""),
                "description": doc_info.get("description", ""),
                "tags": doc_info.get("tags", []),
                "converted": doc_info.get("process", {}).get("stages", {}).get("conversion", {}).get("success", False),
                "has_markdown": doc_info.get("process", {}).get("current_stage") == ProcessStage.CONVERTED,
                "has_chunks": doc_info.get("process", {}).get("current_stage") == ProcessStage.CHUNKED,
                "source_type": doc_info.get("source_type", "local"),
                "source_url": doc_info.get("source_url", ""),
                **{k: v for k, v in doc_info.items() 
                  if k not in ["document_id", "original_name", "size", "type", "extension", "path", 
                              "created_at", "updated_at", "status", "title", "description", 
                              "tags", "process", "source_type", "source_url"]}
            })
        
        return result
    
    @handle_errors()
    async def get_document_info(
        document_id: str,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """获取文档信息和元数据"""
        user_id = token_claims["user_id"]
        
        doc_info = await documents_service.get_document_meta(user_id, document_id)
        if not doc_info or doc_info.get("status") != DocumentStatus.ACTIVE:
            raise HTTPException(status_code=404, detail="文档不存在")
        
        # 确定下载URL
        download_url = None
        if doc_info.get("source_type") == "local":
            download_url = f"{prefix}/documents/{document_id}/download"
        
        return {
            "document_id": doc_info["document_id"],
            "original_name": doc_info["original_name"],
            "size": doc_info.get("size", 0),
            "type": doc_info.get("type", ""),
            "extension": doc_info.get("extension", ""),
            "created_at": doc_info["created_at"],
            "updated_at": doc_info.get("updated_at", doc_info["created_at"]),
            "download_url": download_url,
            "title": doc_info.get("title", ""),
            "description": doc_info.get("description", ""),
            "tags": doc_info.get("tags", []),
            "converted": doc_info.get("process", {}).get("stages", {}).get("conversion", {}).get("success", False),
            "has_markdown": doc_info.get("process", {}).get("current_stage") == ProcessStage.CONVERTED,
            "has_chunks": doc_info.get("process", {}).get("current_stage") == ProcessStage.CHUNKED,
            "source_type": doc_info.get("source_type", "local"),
            "source_url": doc_info.get("source_url", ""),
            **{k: v for k, v in doc_info.items() 
               if k not in ["document_id", "original_name", "size", "type", "extension", "path", 
                           "created_at", "updated_at", "status", "title", "description", 
                           "tags", "process", "markdown_content"]}
        }
    
    @handle_errors()
    async def update_document_metadata(
        document_id: str,
        metadata: DocumentMetadataUpdate,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """更新文档元数据"""
        user_id = token_claims["user_id"]
        
        # 构建元数据字典
        update_data = {}
        
        if metadata.title is not None:
            update_data["title"] = metadata.title
            
        if metadata.description is not None:
            update_data["description"] = metadata.description
            
        if metadata.tags is not None:
            update_data["tags"] = metadata.tags
            
        # 额外字段
        if metadata.extra_fields:
            update_data.update(metadata.extra_fields)
        
        success = await documents_service.update_metadata(user_id, document_id, update_data)
        if not success:
            raise HTTPException(status_code=404, detail="文档不存在或无法更新")
        
        # 获取更新后的文档信息
        return await documents_service.get_document_meta(user_id, document_id)
    
    @handle_errors()
    async def delete_document(
        document_id: str,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """删除文档"""
        user_id = token_claims["user_id"]
        
        success = await documents_service.delete_document(user_id, document_id)
        if not success:
            raise HTTPException(status_code=404, detail="文档不存在或无法删除")
        
        return {"success": True, "message": "文档已删除"}
    
    @handle_errors()
    async def download_document(
        document_id: str,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """下载原始文档"""
        user_id = token_claims["user_id"]
        
        try:
            doc_info = await documents_service.get_document_meta(user_id, document_id)
            if not doc_info or doc_info.get("status") != DocumentStatus.ACTIVE:
                raise HTTPException(status_code=404, detail="文档不存在")
            
            # 判断文档类型
            if doc_info.get("source_type") == "remote":
                # 远程文档无法下载原始内容
                source_url = doc_info.get("source_url")
                if not source_url:
                    raise HTTPException(status_code=404, detail="远程文档没有可用的源URL")
                
                # 返回URL信息
                return {
                    "success": False,
                    "message": "这是一个远程资源，请直接使用原始链接下载",
                    "source_url": source_url
                }
            
            # 本地文档
            file_path = documents_service.get_raw_path(user_id, document_id)
            if not file_path.exists():
                raise HTTPException(status_code=404, detail="原始文档不存在")
            
            return FileResponse(
                path=file_path,
                filename=doc_info["original_name"],
                media_type=documents_service.get_file_mimetype(doc_info["original_name"])
            )
        except Exception as e:
            logger.error(f"下载文档失败: {str(e)}")
            raise HTTPException(status_code=500, detail="下载文档失败")
    
    @handle_errors()
    async def get_storage_status(
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """获取用户存储状态"""
        user_id = token_claims["user_id"]
        
        try:
            usage = await documents_service.calculate_storage_usage(user_id)
            documents = await documents_service.list_documents(user_id)
            
            return {
                "used": usage,
                "limit": documents_service.max_total_size_per_user,
                "available": documents_service.max_total_size_per_user - usage,
                "usage_percentage": round(usage * 100 / documents_service.max_total_size_per_user, 2),
                "document_count": len(documents),
                "last_updated": time.time()
            }
        except Exception as e:
            logger.error(f"获取存储状态失败: {str(e)}")
            raise HTTPException(status_code=500, detail="获取存储状态失败")
    
    @handle_errors()
    async def upload_document(
        file: UploadFile = File(...),
        title: Optional[str] = Form(None),
        description: Optional[str] = Form(None),
        tags: Optional[str] = Form(None),
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """上传文档"""
        user_id = token_claims["user_id"]
        logger.info(f"上传文档请求: 用户ID={user_id}, 文件名={file.filename}")
        
        try:
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
            
            # 保存文档
            doc_info = await documents_service.save_document(user_id, file, metadata)
            
            # 返回基本文档信息
            return {
                "success": True,
                "document_id": doc_info["document_id"],
                "original_name": doc_info["original_name"],
                "size": doc_info["size"],
                "type": doc_info["type"],
                "extension": doc_info.get("extension", ""),
                "created_at": doc_info["created_at"],
                "status": DocumentStatus.ACTIVE,
                "download_url": f"{prefix}/documents/{doc_info['document_id']}/download",
            }
        except ValueError as e:
            logger.error(f"文档上传失败: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"文档上传失败: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @handle_errors()
    async def bookmark_remote_document(
        bookmark: BookmarkUrlRequest,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """收藏远程URL文档"""
        user_id = token_claims["user_id"]
        logger.info(f"收藏远程文档请求: 用户ID={user_id}, URL={bookmark.url}")
        
        try:
            # 确定文件名
            filename = bookmark.filename
            if not filename:
                import urllib.parse
                filename = os.path.basename(urllib.parse.urlparse(str(bookmark.url)).path) or "remote_document"
                if not filename.strip():
                    filename = "remote_document.html"
            
            # 准备元数据
            metadata = {}
            if bookmark.title:
                metadata["title"] = bookmark.title
            if bookmark.description:
                metadata["description"] = bookmark.description
            if bookmark.tags:
                metadata["tags"] = bookmark.tags
            
            # 创建远程文档记录
            doc_info = await documents_service.create_remote_document(
                user_id=user_id,
                url=str(bookmark.url),
                filename=filename,
                metadata=metadata
            )
            
            # 返回基本文档信息
            return {
                "success": True,
                "document_id": doc_info["document_id"],
                "original_name": doc_info["original_name"],
                "type": doc_info["type"],
                "extension": doc_info.get("extension", ""),
                "created_at": doc_info["created_at"],
                "status": DocumentStatus.ACTIVE,
                "source_type": "remote",
                "source_url": str(bookmark.url)
            }
        except Exception as e:
            logger.error(f"收藏远程文档失败: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
            
    # 返回路由列表，格式为(HTTP方法, 路径, 处理函数)
    return [
        (HttpMethod.GET,  f"{prefix}/documents", list_documents),
        (HttpMethod.GET,  f"{prefix}/documents/{{document_id}}", get_document_info),
        (HttpMethod.PUT, f"{prefix}/documents/{{document_id}}", update_document_metadata),
        (HttpMethod.DELETE, f"{prefix}/documents/{{document_id}}", delete_document),
        (HttpMethod.GET,  f"{prefix}/documents/{{document_id}}/download", download_document),
        (HttpMethod.GET,  f"{prefix}/documents/storage/status", get_storage_status),
        (HttpMethod.POST, f"{prefix}/documents/upload", upload_document),
        (HttpMethod.POST, f"{prefix}/documents/bookmark", bookmark_remote_document),
    ]