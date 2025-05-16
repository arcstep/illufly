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
import mimetypes

from soulseal import TokenSDK
from ..schemas import Result, HttpMethod
from ..http import handle_errors
from ...documents.service import DocumentService

# 文档元数据更新请求模型
class DocumentMetadataUpdate(BaseModel):
    """文档元数据更新请求"""
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    summary: Optional[str] = None
    is_public: Optional[bool] = None
    allowed_roles: Optional[List[str]] = None
    topic_path: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

# 远程URL书签请求模型
class BookmarkUrlRequest(BaseModel):
    """远程URL书签请求"""
    url: HttpUrl
    filename: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None

# 文档状态查询请求模型
class DocumentStatusRequest(BaseModel):
    """文档状态查询请求"""
    document_ids: List[str]

def create_documents_endpoints(
    app: FastAPI,
    token_sdk: TokenSDK,
    document_service: DocumentService,
    prefix: str = "/api",
    logger: logging.Logger = None
) -> List[Tuple[HttpMethod, str, Callable]]:
    """创建文档管理相关的API端点
    
    Args:
        app: FastAPI应用实例
        token_sdk: 令牌SDK
        document_service: 文档服务
        prefix: API前缀
        logger: 日志记录器
    
    Returns:
        List[Tuple[HttpMethod, str, Callable]]: 
            元组列表 (HTTP方法, 路由路径, 处理函数)
    """
    logger = logger or logging.getLogger(__name__)
    require_user = token_sdk.get_auth_dependency(logger=logger)

    # 定义允许直接提取的字段列表
    DOCUMENT_FIELDS = [
        "document_id", "original_name", "size", "type", "extension", 
        "created_at", "updated_at", "status", "title", "description", "tags", 
        "source_type", "source_url", "chunks_count", "state", "sub_state"
    ]
    
    def format_document_info(doc_info, prefix, include_details=False):
        """将文档元数据转换为标准响应格式"""
        # 基础结果
        result = {k: doc_info.get(k) for k in DOCUMENT_FIELDS if k in doc_info}
        
        # 状态字段保持原样，不做额外处理
        current_state = doc_info.get("state", "init")
        sub_state = doc_info.get("sub_state", "none")
        
        # 下载URL - 仅本地文件可下载
        if doc_info.get("source_type") == "local":
            result["download_url"] = f"{prefix}/documents/{doc_info['document_id']}/download"
        else:
            result["download_url"] = None
        
        # 移除冗余字段，只保留必要的兼容性字段
        result["is_processing"] = sub_state == "processing"
        
        # 包含详细信息
        if include_details:
            result["resources"] = doc_info.get("resources", {})
            result["state_history"] = doc_info.get("state_history", [])
        
        return result
    
    @handle_errors()
    async def list_documents(
        request: Request,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """获取用户所有文档"""
        user_id = token_claims["user_id"]
        documents = await document_service.list_documents(user_id)
        return [format_document_info(doc, prefix) for doc in documents]
    
    @handle_errors()
    async def get_document_info(
        document_id: str,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """获取文档信息和元数据"""
        user_id = token_claims["user_id"]
        doc_info = await document_service.get_document(user_id, document_id)
        if not doc_info:
            raise HTTPException(status_code=404, detail="文档不存在")
        return format_document_info(doc_info, prefix, include_details=True)
    
    @handle_errors()
    async def update_document_metadata(
        document_id: str,
        metadata: DocumentMetadataUpdate,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """更新文档元数据"""
        user_id = token_claims["user_id"]
        
        # 直接传递所有参数给service
        result = await document_service.update_document_metadata(
            user_id, 
            document_id,
            title=metadata.title,
            description=metadata.description,
            tags=metadata.tags,
            summary=metadata.summary,
            is_public=metadata.is_public,
            allowed_roles=metadata.allowed_roles,
            topic_path=metadata.topic_path,
            metadata=metadata.metadata  # 传递额外元数据
        )
        
        if not result.success:
            raise HTTPException(
                status_code=404, 
                detail=result.error_message or "文档不存在或无法更新"
            )
        
        return result.data
    
    @handle_errors()
    async def delete_document(
        document_id: str,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """删除文档"""
        user_id = token_claims["user_id"]
        result = await document_service.delete_document(user_id, document_id)
        if not result.success:
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
            doc_info = await document_service.get_document(user_id, document_id)
            if not doc_info:
                raise HTTPException(status_code=404, detail="文档不存在")
            
            # 判断文档类型
            if doc_info.get("source_type") == "remote":
                # 远程文档无法下载
                source_url = doc_info.get("source_url")
                if not source_url:
                    raise HTTPException(status_code=404, detail="远程文档没有可用的源URL")
                return {
                    "success": False,
                    "message": "这是一个远程资源，请直接使用原始链接下载",
                    "source_url": source_url
                }
            
            # 本地文档
            file_path = document_service.processor.get_raw_path(user_id, document_id)
            if not file_path.exists():
                raise HTTPException(status_code=404, detail="原始文档不存在")
            
            # 获取MIME类型
            mimetype, _ = mimetypes.guess_type(doc_info["original_name"])
            return FileResponse(
                path=file_path,
                filename=doc_info["original_name"],
                media_type=mimetype or "application/octet-stream"
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
            usage = await document_service.processor.calculate_storage_usage(user_id)
            documents = await document_service.list_documents(user_id)
            
            return {
                "used": usage,
                "limit": document_service.max_total_size_per_user,
                "available": document_service.max_total_size_per_user - usage,
                "usage_percentage": round(usage * 100 / document_service.max_total_size_per_user, 2),
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
        metadata: Optional[str] = Form(None),  # 新增: 接收自定义元数据的JSON字符串
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """上传文档"""
        user_id = token_claims["user_id"]
        logger.info(f"上传文档请求: 用户ID={user_id}, 文件名={file.filename}")
        
        try:
            # 文件类型检查 - 从processor获取允许的扩展名
            allowed_extensions = document_service.processor.allowed_extensions
            file_ext = os.path.splitext(file.filename)[1].lower()
            
            if file_ext not in allowed_extensions:
                supported_ext = ', '.join(allowed_extensions)
                raise ValueError(f"不支持的文件类型: {file_ext}。支持的类型: {supported_ext}")
            
            # 准备元数据
            meta_dict = {}
            if title:
                meta_dict["title"] = title
            if description:
                meta_dict["description"] = description
            if tags:
                try:
                    meta_dict["tags"] = json.loads(tags)
                except:
                    meta_dict["tags"] = [t.strip() for t in tags.split(',') if t.strip()]
            
            # 处理自定义元数据
            if metadata:
                try:
                    custom_metadata = json.loads(metadata)
                    # 合并自定义元数据
                    meta_dict.update(custom_metadata)
                except json.JSONDecodeError:
                    logger.warning(f"解析自定义元数据失败: {metadata}")
            
            result = await document_service.upload_document(user_id, file, metadata=meta_dict)
            if not result.success:
                raise HTTPException(status_code=400, detail=result.error_message)
            
            doc_info = result.data
            return {
                "success": True,
                "document_id": doc_info["document_id"],
                "original_name": doc_info["original_name"],
                "size": doc_info["size"],
                "type": doc_info["type"],
                "extension": doc_info.get("extension", ""),
                "created_at": doc_info["created_at"],
                "status": "active",
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
            # 准备元数据
            metadata = {}
            if bookmark.title:
                metadata["title"] = bookmark.title
            if bookmark.description:
                metadata["description"] = bookmark.description
            if bookmark.tags:
                metadata["tags"] = bookmark.tags
            
            result = await document_service.create_bookmark(
                user_id=user_id,
                url=str(bookmark.url),
                filename=bookmark.filename or "remote_document.html",
                metadata=metadata
            )
            
            if not result.success:
                raise HTTPException(status_code=400, detail=result.error_message)
            
            doc_info = result.data
            return {
                "success": True,
                "document_id": doc_info["document_id"],
                "original_name": doc_info["original_name"],
                "type": doc_info["type"],
                "extension": doc_info.get("extension", ""),
                "created_at": doc_info["created_at"],
                "status": "active",
                "source_type": "remote",
                "source_url": str(bookmark.url)
            }
        except Exception as e:
            logger.error(f"收藏远程文档失败: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @handle_errors()
    async def convert_to_markdown(
        document_id: str,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """将文档转换为Markdown格式"""
        user_id = token_claims["user_id"]
        logger.info(f"文档转换为Markdown请求: 用户ID={user_id}, 文档ID={document_id}")
        
        try:
            doc_info = await document_service.get_document(user_id, document_id)
            if not doc_info:
                raise HTTPException(status_code=404, detail="文档不存在")
            
            # 检查是否在处理中
            current_state = doc_info.get("state")
            sub_state = doc_info.get("sub_state")
            if sub_state == "processing":
                return {
                    "success": False,
                    "document_id": document_id,
                    "message": f"文档处理已在进行中: {current_state}",
                    "current_state": current_state
                }
            
            result = await document_service.convert_to_markdown(user_id, document_id)
            if not result.success:
                raise HTTPException(status_code=400, detail=result.error_message)
            
            return {
                "success": True,
                "document_id": document_id,
                "message": "文档转换已启动",
                "current_state": result.data.get("state", "markdowned"),
                "is_processing": result.data.get("sub_state") == "processing"
            }
        except Exception as e:
            logger.error(f"文档转换失败: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @handle_errors()
    async def get_document_markdown(
        document_id: str,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """获取文档的Markdown内容"""
        user_id = token_claims["user_id"]
        logger.info(f"获取Markdown内容请求: 用户ID={user_id}, 文档ID={document_id}")
        
        try:
            result = await document_service.get_markdown(user_id, document_id)
            if not result.success:
                raise HTTPException(status_code=404, detail=result.error_message)
            
            return {
                "success": True,
                "document_id": document_id,
                "content": result.data.get("content"),
                "length": len(result.data.get("content", ""))
            }
        except Exception as e:
            logger.error(f"获取Markdown内容失败: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @handle_errors()
    async def chunk_document(
        document_id: str,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """将文档切片处理"""
        user_id = token_claims["user_id"]
        logger.info(f"文档切片请求: 用户ID={user_id}, 文档ID={document_id}")
        
        try:
            doc_info = await document_service.get_document(user_id, document_id)
            if not doc_info:
                raise HTTPException(status_code=404, detail="文档不存在")
            
            # 检查文档是否处于可切片状态
            if doc_info.get("sub_state") == "processing":
                raise HTTPException(status_code=400, detail=f"文档处理进行中: {doc_info['state']}")
            elif doc_info['state'] in ["init", "uploaded", "bookmarked"]:
                raise HTTPException(status_code=400, detail="文档必须先转换为Markdown才能进行切片")
            elif doc_info['state'] in ["chunked", "embedded"]:
                # 已经完成切片或更高阶段
                return {
                    "success": True,
                    "document_id": document_id,
                    "message": "文档已完成切片",
                    "current_state": doc_info['state'],
                    "chunks_count": doc_info.get("chunks_count", 0)
                }
            
            result = await document_service.chunk_document(user_id, document_id)
            
            return {
                "success": True,
                "document_id": document_id,
                "message": "文档切片处理完成",
                "current_state": result.data.get("state", "chunked"),
                "chunks_count": result.data.get("chunks_count", 0)
            }
        except Exception as e:
            logger.error(f"文档切片失败: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @handle_errors()
    async def get_document_chunks(
        document_id: str,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """获取文档的所有切片"""
        user_id = token_claims["user_id"]
        logger.info(f"获取文档切片请求: 用户ID={user_id}, 文档ID={document_id}")
        
        try:
            result = await document_service.get_chunks(user_id, document_id)
            if not result.success:
                raise HTTPException(status_code=404, detail=result.error_message)
            
            chunks = result.data.get("chunks", [])
            return {
                "success": True,
                "chunks_count": len(chunks),
                "chunks": chunks
            }
        except Exception as e:
            logger.error(f"获取文档切片失败: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @handle_errors()
    async def index_document(
        document_id: str,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """将文档添加到向量索引"""
        user_id = token_claims["user_id"]
        logger.info(f"文档索引请求: 用户ID={user_id}, 文档ID={document_id}")
        
        try:
            doc_info = await document_service.get_document(user_id, document_id)
            if not doc_info:
                raise HTTPException(status_code=404, detail="文档不存在")
            
            # 检查文档是否处于可索引状态
            if doc_info.get("sub_state") == "processing":
                raise HTTPException(status_code=400, detail=f"文档处理进行中: {doc_info['state']}")
            elif doc_info['state'] in ["init", "uploaded", "bookmarked", "markdowned"]:
                raise HTTPException(status_code=400, detail="文档必须先完成切片才能创建索引")
            elif doc_info['state'] == "embedded":
                # 已经完成嵌入
                return {
                    "success": True,
                    "document_id": document_id,
                    "message": "文档已完成索引",
                    "current_state": doc_info['state'],
                    "indexed_chunks": doc_info.get("vectors_count", 0)
                }
            
            result = await document_service.generate_embeddings(user_id, document_id)
            
            return {
                "success": True,
                "document_id": document_id,
                "message": "文档索引创建完成",
                "current_state": result.data.get("state", "embedded"),
                "indexed_chunks": result.data.get("vectors_count", 0)
            }
        except Exception as e:
            logger.error(f"创建文档索引失败: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @handle_errors()
    async def search_documents(
        query: str,
        document_id: Optional[str] = None,
        limit: Optional[int] = 10,
        filter_metadata: Optional[str] = None,  # 新增: 接收元数据过滤条件
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """搜索文档内容"""
        user_id = token_claims["user_id"]
        logger.info(f"文档搜索请求: 用户ID={user_id}, 查询={query}, 文档ID={document_id}")
        
        try:
            # 解析元数据过滤条件
            filter_condition = None
            if filter_metadata:
                try:
                    filter_dict = json.loads(filter_metadata)
                    conditions = []
                    for key, value in filter_dict.items():
                        if isinstance(value, str):
                            conditions.append(f"{key} = '{value}'")
                        elif isinstance(value, (int, float)):
                            conditions.append(f"{key} = {value}")
                        elif isinstance(value, list):
                            values = "', '".join([str(v) for v in value])
                            conditions.append(f"{key} IN ('{values}')")
                    
                    if conditions:
                        filter_condition = " AND ".join(conditions)
                except json.JSONDecodeError:
                    logger.warning(f"解析元数据过滤条件失败: {filter_metadata}")
                
            result = await document_service.search_chunks(
                user_id=user_id,
                query=query,
                document_id=document_id,
                limit=limit,
                filter=filter_condition
            )
            
            if not result.success:
                raise HTTPException(status_code=400, detail=result.error_message)
            
            return {
                "success": True,
                "query": query,
                "results_count": len(result.data.get("matches", [])),
                "results": result.data.get("matches", [])
            }
        except Exception as e:
            logger.error(f"搜索文档失败: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @handle_errors()
    async def get_documents_status(
        request: DocumentStatusRequest,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """获取多个文档的处理状态"""
        user_id = token_claims["user_id"]
        document_ids = request.document_ids
        logger.info(f"批量获取文档状态请求: 用户ID={user_id}, 文档IDs数量={len(document_ids)}")
        
        results = {}
        for document_id in document_ids:
            try:
                doc_meta = await document_service.get_document(user_id, document_id)
                if not doc_meta:
                    results[document_id] = {
                        "found": False,
                        "message": "文档不存在或已删除"
                    }
                    continue
                
                current_state = doc_meta.get("state", "init")
                sub_state = doc_meta.get("sub_state", "none")
                
                results[document_id] = {
                    "found": True,
                    "document_id": document_id,
                    "title": doc_meta.get("title", ""),
                    "original_name": doc_meta.get("original_name", ""),
                    "process_state": current_state,
                    "sub_state": sub_state,
                    "is_processing": sub_state == "processing"
                }
            except Exception as e:
                logger.error(f"获取文档状态失败: {document_id}, 错误: {e}")
                results[document_id] = {
                    "found": False,
                    "error": str(e),
                    "message": "获取文档状态失败"
                }
        
        return {
            "success": True,
            "count": len(document_ids),
            "found_count": sum(1 for doc in results.values() if doc.get("found", False)),
            "results": results
        }
    
    @handle_errors()
    async def move_document_to_topic(
        document_id: str,
        target_topic: Optional[str] = None,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """移动文档到指定主题"""
        user_id = token_claims["user_id"]
        
        result = await document_service.move_document_to_topic(
            user_id, document_id, target_topic
        )
        
        if not result.success:
            raise HTTPException(status_code=400, detail=result.error_message)
        
        return {
            "success": True,
            "document_id": document_id,
            "target_topic": target_topic or "根目录",
            "message": "文档已移动到新位置"
        }
    
    @handle_errors()
    async def list_user_collections(
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """列出用户拥有的向量集合"""
        user_id = token_claims["user_id"]
        logger.info(f"列出向量集合请求: 用户ID={user_id}")
        
        result = await document_service.list_user_collections(user_id)
        if not result.success:
            raise HTTPException(status_code=400, detail=result.error_message)
        
        return {
            "success": True,
            "collections": result.data.get("collections", []),
            "total": result.data.get("total", 0)
        }
    
    # 返回路由列表，格式为(HTTP方法, 路径, 处理函数)
    return [
        (HttpMethod.GET,  f"{prefix}/documents", list_documents),
        (HttpMethod.GET,  f"{prefix}/documents/{{document_id}}", get_document_info),
        (HttpMethod.PUT, f"{prefix}/documents/{{document_id}}", update_document_metadata),
        (HttpMethod.DELETE, f"{prefix}/documents/{{document_id}}", delete_document),
        (HttpMethod.POST, f"{prefix}/documents/{{document_id}}/move", move_document_to_topic),
        (HttpMethod.GET,  f"{prefix}/documents/{{document_id}}/download", download_document),
        (HttpMethod.GET,  f"{prefix}/documents/storage/status", get_storage_status),
        (HttpMethod.POST, f"{prefix}/documents/upload", upload_document),
        (HttpMethod.POST, f"{prefix}/documents/bookmark", bookmark_remote_document),
        (HttpMethod.POST, f"{prefix}/documents/{{document_id}}/convert", convert_to_markdown),
        (HttpMethod.GET,  f"{prefix}/documents/{{document_id}}/markdown", get_document_markdown),
        (HttpMethod.POST, f"{prefix}/documents/{{document_id}}/chunks", chunk_document),
        (HttpMethod.GET,  f"{prefix}/documents/{{document_id}}/chunks", get_document_chunks),
        (HttpMethod.POST, f"{prefix}/documents/{{document_id}}/index", index_document),
        (HttpMethod.POST, f"{prefix}/documents/chunks/search", search_documents),
        (HttpMethod.POST, f"{prefix}/documents/status", get_documents_status),
        (HttpMethod.GET,  f"{prefix}/documents/collections", list_user_collections),
    ]