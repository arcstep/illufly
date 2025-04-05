from typing import List, Dict, Any, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Body
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
import logging
import os
import time
from pathlib import Path
from pydantic import BaseModel, HttpUrl

from ...upload.base import UploadService, FileStatus
from ...llm.docs import DocumentManager, Document as DocModel, DocumentChunk, DocumentSource
from ...rocksdb import IndexedRocksDB
from ..auth import TokensManager, require_user, TokenClaims
from ..models import HttpMethod

logger = logging.getLogger(__name__)

# 定义请求模型
class WebUrlRequest(BaseModel):
    url: HttpUrl
    title: Optional[str] = None
    description: Optional[str] = ""

def create_docs_endpoints(
    app, 
    tokens_manager: TokensManager, 
    db: IndexedRocksDB,
    file_storage_dir: str = "./uploads",
    prefix: str = "/api"
) -> List[Tuple[str, str, callable]]:
    """创建文档相关的端点
    
    Args:
        app: FastAPI 应用实例
        tokens_manager: Token 管理器
        db: RocksDB 实例
        file_storage_dir: 文件存储目录
        prefix: API 前缀
        
    Returns:
        端点列表
    """
    # 初始化服务
    file_service = UploadService(file_storage_dir)
    doc_manager = DocumentManager(db, file_service)
    
    # 启动清理任务
    @app.on_event("startup")
    async def start_cleanup_task():
        # 启动文件清理任务
        file_service.start_cleanup_task()
    
    # API 启动时初始化向量检索器
    @app.on_event("startup")
    async def init_doc_retriever():
        await doc_manager.init_retriever()
    
    # 关闭时取消任务
    @app.on_event("shutdown")
    async def shutdown_tasks():
        # 取消清理任务
        file_service.cancel_cleanup_task()
    
    async def list_documents(token_claims: TokenClaims = Depends(require_user(tokens_manager, logger=logger))):
        """获取用户所有文档
        
        Args:
            token_claims: 用户Token声明（从token获取）
            
        Returns:
            文档列表
        """
        user_id = token_claims['user_id']
        
        # 获取文档列表
        docs = await doc_manager.get_documents(user_id)
        
        # 转换为前端格式
        result = []
        for doc in docs:
            result.append({
                "id": doc.id,
                "title": doc.title,
                "description": doc.description,
                "type": doc.type,
                "source_type": doc.source_type,
                "source": doc.source,
                "created_at": doc.created_at,
                "chunks_count": doc.chunks_count,
                "file_url": file_service.get_download_url(user_id, doc.id) if doc.source_type == DocumentSource.UPLOAD else None
            })
        
        return result
    
    async def get_document(
        doc_id: str, 
        token_claims: TokenClaims = Depends(require_user(tokens_manager, logger=logger))
    ):
        """获取文档详情
        
        Args:
            doc_id: 文档ID
            token_claims: 用户Token声明（从token获取）
            
        Returns:
            文档详情
        """
        user_id = token_claims['user_id']
        
        # 获取文档
        doc = await doc_manager.get_document(user_id, doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")
        
        # 转换为前端格式
        return {
            "id": doc.id,
            "title": doc.title,
            "description": doc.description,
            "type": doc.type,
            "source_type": doc.source_type,
            "source": doc.source,
            "created_at": doc.created_at,
            "chunks_count": doc.chunks_count,
            "file_url": file_service.get_download_url(user_id, doc.id) if doc.source_type == DocumentSource.UPLOAD else None
        }
    
    async def upload_document(
        file: UploadFile = File(...), 
        title: str = Form(None),
        description: str = Form(""),
        token_claims: TokenClaims = Depends(require_user(tokens_manager, logger=logger))
    ):
        """上传文档
        
        Args:
            file: 上传的文件
            title: 文档标题（可选，默认使用文件名）
            description: 文档描述（可选）
            token_claims: 用户Token声明（从token获取）
            
        Returns:
            上传成功的文档信息
        """
        user_id = token_claims['user_id']
        
        try:
            # 保存文件
            file_info = await file_service.save_file(user_id, file)
            
            # 处理文档（切片、向量化）
            doc = await doc_manager.process_upload(
                user_id=user_id,
                file_info=file_info,
                title=title,
                description=description
            )
            
            # 返回文档信息
            return {
                "id": doc.id,
                "title": doc.title,
                "description": doc.description,
                "type": doc.type,
                "source_type": doc.source_type,
                "source": doc.source,
                "created_at": doc.created_at,
                "chunks_count": doc.chunks_count,
                "file_url": file_service.get_download_url(user_id, doc.id)
            }
            
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"上传文档失败: {str(e)}")
            raise HTTPException(status_code=500, detail="上传文档失败")
    
    async def add_web_document(
        web_request: WebUrlRequest,
        token_claims: TokenClaims = Depends(require_user(tokens_manager, logger=logger))
    ):
        """添加网页文档
        
        Args:
            web_request: 网页请求对象
            token_claims: 用户Token声明（从token获取）
            
        Returns:
            处理成功的文档信息
        """
        user_id = token_claims['user_id']
        
        try:
            # 处理网页URL
            doc = await doc_manager.process_web_url(
                user_id=user_id,
                url=str(web_request.url),
                title=web_request.title,
                description=web_request.description
            )
            
            # 返回文档信息
            return {
                "id": doc.id,
                "title": doc.title,
                "description": doc.description,
                "type": doc.type,
                "source_type": doc.source_type,
                "source": doc.source,
                "created_at": doc.created_at,
                "chunks_count": doc.chunks_count,
                "file_url": None  # 网页文档没有下载链接
            }
            
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"处理网页文档失败: {str(e)}")
            raise HTTPException(status_code=500, detail="处理网页文档失败")
    
    async def download_document(
        doc_id: str, 
        token_claims: TokenClaims = Depends(require_user(tokens_manager, logger=logger))
    ):
        """下载文档
        
        Args:
            doc_id: 文档ID
            token_claims: 用户Token声明（从token获取）
            
        Returns:
            文件内容
        """
        user_id = token_claims['user_id']
        
        # 获取文档
        doc = await doc_manager.get_document(user_id, doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")
        
        # 如果是网页文档，返回错误
        if doc.source_type == DocumentSource.WEB:
            raise HTTPException(status_code=400, detail="网页文档不支持下载，请访问原始URL")
        
        # 获取文件路径
        file_path = Path(doc.file_path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")
        
        # 返回文件
        return FileResponse(
            path=file_path,
            filename=f"{doc.title}.{doc.type}",
            media_type=file_service.get_file_mimetype(file_path.name)
        )
    
    async def delete_document(
        doc_id: str, 
        token_claims: TokenClaims = Depends(require_user(tokens_manager, logger=logger))
    ):
        """删除文档
        
        Args:
            doc_id: 文档ID
            token_claims: 用户Token声明（从token获取）
            
        Returns:
            删除结果
        """
        user_id = token_claims['user_id']
        
        # 删除文档及切片
        result = await doc_manager.delete_document(user_id, doc_id)
        if not result:
            raise HTTPException(status_code=404, detail="文档不存在")
        
        return {"success": True}
    
    async def get_document_chunks(
        doc_id: str, 
        token_claims: TokenClaims = Depends(require_user(tokens_manager, logger=logger))
    ):
        """获取文档切片
        
        Args:
            doc_id: 文档ID
            token_claims: 用户Token声明（从token获取）
            
        Returns:
            切片列表
        """
        user_id = token_claims['user_id']
        
        # 获取文档
        doc = await doc_manager.get_document(user_id, doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")
        
        # 获取切片
        chunks = await doc_manager.get_chunks(user_id, doc_id)
        
        # 转换为前端格式
        result = []
        for chunk in chunks:
            result.append({
                "id": chunk.id,
                "content": chunk.content,
                "sequence": chunk.sequence,
                "created_at": chunk.created_at
            })
        
        return result
    
    async def search_document_chunks(
        doc_id: str, 
        q: str = Query(..., min_length=1),
        token_claims: TokenClaims = Depends(require_user(tokens_manager, logger=logger))
    ):
        """搜索文档切片
        
        Args:
            doc_id: 文档ID
            q: 搜索查询
            token_claims: 用户Token声明（从token获取）
            
        Returns:
            匹配的切片列表
        """
        user_id = token_claims['user_id']
        
        # 获取文档
        doc = await doc_manager.get_document(user_id, doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")
        
        # 搜索切片
        chunks = await doc_manager.search_chunks(user_id, doc_id, q)
        
        # 转换为前端格式
        result = []
        for chunk in chunks:
            result.append({
                "id": chunk.id,
                "content": chunk.content,
                "sequence": chunk.sequence,
                "created_at": chunk.created_at
            })
        
        return result
    
    async def search_documents(
        q: str = Query(..., min_length=1),
        token_claims: TokenClaims = Depends(require_user(tokens_manager, logger=logger))
    ):
        """搜索文档
        
        Args:
            q: 搜索查询
            token_claims: 用户Token声明（从token获取）
            
        Returns:
            匹配的文档列表
        """
        user_id = token_claims['user_id']
        
        # 搜索文档
        results = await doc_manager.search_documents(user_id, q)
        
        # 转换为前端格式
        docs = []
        for doc, chunks in results:
            docs.append({
                "id": doc.id,
                "title": doc.title,
                "description": doc.description,
                "type": doc.type,
                "source_type": doc.source_type,
                "source": doc.source,
                "created_at": doc.created_at,
                "chunks_count": doc.chunks_count,
                "file_url": file_service.get_download_url(user_id, doc.id) if doc.source_type == DocumentSource.UPLOAD else None,
                "matched_chunks": [
                    {
                        "id": chunk.id,
                        "content": chunk.content,
                        "sequence": chunk.sequence,
                        "created_at": chunk.created_at
                    } for chunk in chunks[:3]  # 每个文档只返回最多3个匹配的切片
                ]
            })
        
        return docs
    
    # 返回端点列表
    return [
        (HttpMethod.GET, f"{prefix}/docs", list_documents),
        (HttpMethod.GET, f"{prefix}/docs/search", search_documents),
        (HttpMethod.POST, f"{prefix}/docs/upload", upload_document),
        (HttpMethod.POST, f"{prefix}/docs/web", add_web_document),
        (HttpMethod.GET, f"{prefix}/docs/{{doc_id}}", get_document),
        (HttpMethod.DELETE, f"{prefix}/docs/{{doc_id}}", delete_document),
        (HttpMethod.GET, f"{prefix}/docs/{{doc_id}}/download", download_document),
        (HttpMethod.GET, f"{prefix}/docs/{{doc_id}}/chunks", get_document_chunks),
        (HttpMethod.GET, f"{prefix}/docs/{{doc_id}}/search", search_document_chunks),
    ]
