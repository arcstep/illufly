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
from ...documents.base import DocumentService, DocumentStatus

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

# 文档状态查询请求模型
class DocumentStatusRequest(BaseModel):
    """文档状态查询请求"""
    document_ids: List[str]

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

    # 定义允许直接提取的字段列表
    DOCUMENT_FIELDS = [
        "document_id", "original_name", "size", "type", "extension", 
        "created_at", "updated_at", "status", "title", "description", 
        "tags", "has_markdown", "has_chunks", "has_embeddings", 
        "source_type", "source_url", "chunks_count"
    ]
    
    def format_document_info(doc_info, prefix, include_details=False):
        """将文档元数据转换为标准响应格式"""
        # 基础结果
        result = {k: doc_info.get(k) for k in DOCUMENT_FIELDS if k in doc_info}
        
        # 获取状态 - 使用新字段
        current_state = doc_info.get("state", "ready")
        
        # 下载URL - 仅本地文件可下载
        if doc_info.get("source_type") == "local":
            result["download_url"] = f"{prefix}/documents/{doc_info['document_id']}/download"
        else:
            result["download_url"] = None
            
        # 处理状态相关字段
        result["process_stage"] = current_state  # 直接使用状态机状态
        result["is_processing"] = current_state in ["markdowning", "chunking", "embedding"]
        
        # 兼容性字段
        result["converted"] = doc_info.get("has_markdown", False)
        
        # 包含详细阶段信息
        if include_details:
            process_details = doc_info.get("process_details", {})
            result["stages_detail"] = {
                "markdowning": process_details.get("markdowning", {}),
                "chunking": process_details.get("chunking", {}),
                "embedding": process_details.get("embedding", {})
            }
            
        return result
    
    @handle_errors()
    async def list_documents(
        request: Request,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """获取用户所有文档"""
        user_id = token_claims["user_id"]
        documents = await documents_service.list_documents(user_id)
        
        # 使用通用格式化函数转换为前端格式
        return [format_document_info(doc, prefix) for doc in documents]
    
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
        
        # 使用通用格式化函数，包含详细信息
        return format_document_info(doc_info, prefix, include_details=True)
    
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
    
    @handle_errors()
    async def convert_to_markdown(
        document_id: str,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """将文档转换为Markdown格式"""
        user_id = token_claims["user_id"]
        logger.info(f"文档转换为Markdown请求: 用户ID={user_id}, 文档ID={document_id}")
        
        try:
            # 检查文档是否存在
            doc_info = await documents_service.get_document_meta(user_id, document_id)
            if not doc_info or doc_info.get("status") != DocumentStatus.ACTIVE:
                raise HTTPException(status_code=404, detail="文档不存在")
            
            # 检查是否正在处理中
            current_state = doc_info.get("state", "ready")
            processing_states = ["markdowning", "chunking", "embedding"]
            if current_state in processing_states:
                return {
                    "success": False,
                    "document_id": document_id,
                    "message": f"文档处理已在进行中: {current_state}",
                    "current_state": current_state
                }
            
            # 启动转换过程 - 不提供markdown_content参数，让服务自动转换
            updated_meta = await documents_service.save_markdown(user_id, document_id)
            
            # 返回结果
            return {
                "success": True,
                "document_id": document_id,
                "message": "文档转换已启动",
                "current_state": updated_meta.get("state", "ready"),
                "is_processing": True
            }
        except FileNotFoundError as e:
            logger.error(f"文档转换失败: {str(e)}")
            raise HTTPException(status_code=404, detail=str(e))
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
            # 使用服务中的get_markdown方法获取内容
            markdown_content = await documents_service.get_markdown(user_id, document_id)
            
            return {
                "success": True,
                "document_id": document_id,
                "content": markdown_content,
                "length": len(markdown_content)
            }
        except FileNotFoundError as e:
            logger.error(f"获取Markdown内容失败: {str(e)}")
            raise HTTPException(status_code=404, detail=str(e))
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
            # 检查文档是否存在
            doc_info = await documents_service.get_document_meta(user_id, document_id)
            if not doc_info or doc_info.get("status") != DocumentStatus.ACTIVE:
                raise HTTPException(status_code=404, detail="文档不存在")
            
            # 检查文档是否已转换为Markdown
            current_state = doc_info.get("state", "ready")
            
            if current_state != "markdowned":
                if current_state in ["markdowning", "chunking", "embedding"]:
                    raise HTTPException(status_code=400, detail=f"文档处理进行中: {current_state}")
                elif current_state == "ready":
                    raise HTTPException(status_code=400, detail="文档必须先转换为Markdown才能进行切片")
                elif current_state == "chunked" or current_state == "embedded":
                    # 已经完成切片或更高阶段
                    return {
                        "success": True,
                        "document_id": document_id,
                        "message": "文档已完成切片",
                        "current_state": current_state,
                        "chunks_count": doc_info.get("chunks_count", 0)
                    }
            
            # 启动切片过程 - 不提供chunks参数，让服务自动切片
            success = await documents_service.save_chunks(user_id, document_id)
            
            if not success:
                raise HTTPException(status_code=500, detail="文档切片失败")
            
            # 获取更新后的元数据
            updated_meta = await documents_service.get_document_meta(user_id, document_id)
            
            # 返回结果
            return {
                "success": True,
                "document_id": document_id,
                "message": "文档切片处理完成",
                "current_state": updated_meta.get("state", "ready"),
                "chunks_count": updated_meta.get("chunks_count", 0)
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"文档切片失败: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @handle_errors()
    async def get_document_chunks(
        document_id: str,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """获取文档的所有切片
        
        返回指定文档的切片
        """
        user_id = token_claims["user_id"]
        logger.info(f"获取文档切片请求: 用户ID={user_id}, 文档ID={document_id}")
        
        try:
            # 存储所有切片
            chunks = []
            
            # 获取切片内容
            async for chunk in documents_service.iter_chunks(user_id, document_id):
                chunks.append(chunk)
            
            if document_id and not chunks:
                # 检查文档是否存在
                doc_info = await documents_service.get_document_meta(user_id, document_id)
                if not doc_info:
                    raise HTTPException(status_code=404, detail="文档不存在")
                    
                # 检查文档是否已切片
                chunking_state = doc_info.get("state", "ready")
                if chunking_state != "chunked":
                    raise HTTPException(status_code=400, detail="文档尚未切片或切片处理失败")
            
            return {
                "success": True,
                "chunks_count": len(chunks),
                "chunks": chunks
            }
        except HTTPException:
            raise
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
            # 检查文档是否存在
            doc_info = await documents_service.get_document_meta(user_id, document_id)
            if not doc_info or doc_info.get("status") != DocumentStatus.ACTIVE:
                raise HTTPException(status_code=404, detail="文档不存在")
            
            # 检查文档是否已切片
            current_state = doc_info.get("state", "ready")
            
            if current_state != "chunked":
                if current_state in ["markdowning", "chunking", "embedding"]:
                    raise HTTPException(status_code=400, detail=f"文档处理进行中: {current_state}")
                elif current_state == "ready" or current_state == "markdowned":
                    raise HTTPException(status_code=400, detail="文档必须先完成切片才能创建索引")
                elif current_state == "embedded":
                    # 已经完成嵌入
                    return {
                        "success": True,
                        "document_id": document_id,
                        "message": "文档已完成索引",
                        "current_state": current_state,
                        "indexed_chunks": doc_info.get("vector_index", {}).get("indexed_chunks", 0)
                    }
            
            # 创建索引
            success = await documents_service.create_document_index(user_id, document_id)
            
            if not success:
                raise HTTPException(status_code=500, detail="创建文档索引失败")
            
            # 获取更新后的元数据
            updated_meta = await documents_service.get_document_meta(user_id, document_id)
            
            # 返回结果
            return {
                "success": True,
                "document_id": document_id,
                "message": "文档索引创建完成",
                "current_state": updated_meta.get("state", "ready"),
                "indexed_chunks": updated_meta.get("vector_index", {}).get("indexed_chunks", 0)
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"创建文档索引失败: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @handle_errors()
    async def search_documents(
        query: str,
        document_id: Optional[str] = None,
        limit: Optional[int] = 10,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """搜索文档内容"""
        user_id = token_claims["user_id"]
        logger.info(f"文档搜索请求: 用户ID={user_id}, 查询={query}, 文档ID={document_id}")
        
        try:
            # 检查 documents_service.retriever 是否存在
            logger.info(f"检查 retriever 是否存在: {documents_service.retriever is not None}")
            
            # 执行搜索
            results = await documents_service.search_documents(
                user_id=user_id,
                query=query,
                document_id=document_id,
                limit=limit
            )
            
            logger.info(f"搜索返回结果数量: {len(results)}")
            
            return {
                "success": True,
                "query": query,
                "results_count": len(results),
                "results": results
            }
        except Exception as e:
            logger.error(f"搜索文档失败: {str(e)}")
            logger.exception("搜索异常详情")
            raise HTTPException(status_code=500, detail=str(e))
    
    @handle_errors()
    async def get_documents_status(
        request: DocumentStatusRequest,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """获取多个文档的处理状态
        
        允许客户端同时跟踪多个文档的处理进度变化，如从'正在转换'到'转换完成'
        """
        user_id = token_claims["user_id"]
        document_ids = request.document_ids
        logger.info(f"批量获取文档状态请求: 用户ID={user_id}, 文档IDs数量={len(document_ids)}")
        
        results = {}
        for document_id in document_ids:
            try:
                doc_meta = await documents_service.get_document_meta(user_id, document_id)
                if not doc_meta or doc_meta.get("status") != DocumentStatus.ACTIVE:
                    # 文档不存在或不活跃
                    results[document_id] = {
                        "found": False,
                        "message": "文档不存在或已删除"
                    }
                    continue
                    
                # 获取处理信息
                current_state = doc_meta.get("state", "ready")
                process_details = doc_meta.get("process_details", {})
                
                # 从元数据直接获取
                has_markdown = doc_meta.get("has_markdown", False)
                has_chunks = doc_meta.get("has_chunks", False)
                has_embeddings = doc_meta.get("has_embeddings", False)
                is_processing = current_state in ["markdowning", "chunking", "embedding"]
                
                # 构建响应
                results[document_id] = {
                    "found": True,
                    "document_id": document_id,
                    "title": doc_meta.get("title", ""),
                    "original_name": doc_meta.get("original_name", ""),
                    "process_state": current_state,
                    "is_processing": is_processing,
                    "has_markdown": has_markdown,
                    "has_chunks": has_chunks,
                    "has_embeddings": has_embeddings,
                    "stages_detail": {
                        "markdowning": process_details.get("markdowning", {}),
                        "chunking": process_details.get("chunking", {}),
                        "embedding": process_details.get("embedding", {})
                    }
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
        (HttpMethod.POST, f"{prefix}/documents/{{document_id}}/convert", convert_to_markdown),
        (HttpMethod.GET,  f"{prefix}/documents/{{document_id}}/markdown", get_document_markdown),
        (HttpMethod.POST, f"{prefix}/documents/{{document_id}}/chunks", chunk_document),
        (HttpMethod.GET,  f"{prefix}/documents/{{document_id}}/chunks", get_document_chunks),
        (HttpMethod.POST, f"{prefix}/documents/{{document_id}}/index", index_document),
        (HttpMethod.POST, f"{prefix}/documents/search", search_documents),
        (HttpMethod.POST, f"{prefix}/documents/status", get_documents_status),
    ]