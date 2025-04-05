from typing import List, Dict, Any, Optional
import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form, Query
from pydantic import BaseModel, Field

from ...llm.document_manager import (
    DocumentProcessor, 
    DocumentProcessStatus, 
    DocumentProcessStage,
    DOCLING_AVAILABLE
)
from ...rocksdb import IndexedRocksDB
from ...upload.base import UploadService
from ..auth import require_user, TokenClaims
from ..models import HttpMethod
from ..dependencies import get_indexed_db, get_file_service

logger = logging.getLogger(__name__)

# 创建文档处理器实例
_document_processor: Optional[DocumentProcessor] = None

def get_document_processor(db: IndexedRocksDB = Depends(get_indexed_db)) -> DocumentProcessor:
    """获取文档处理器实例"""
    global _document_processor
    if _document_processor is None:
        _document_processor = DocumentProcessor(db)
    return _document_processor

# API模型定义
class DocumentProcessRequest(BaseModel):
    """文档处理请求"""
    source_path: str = Field(..., description="文档路径或URL")
    doc_id: Optional[str] = Field(None, description="文档ID，如果不提供则自动生成")

class DocumentProcessResponse(BaseModel):
    """文档处理响应"""
    doc_id: str = Field(..., description="文档ID")
    status: DocumentProcessStatus = Field(..., description="处理状态")

class DocumentContentResponse(BaseModel):
    """文档内容响应"""
    doc_id: str = Field(..., description="文档ID")
    content: str = Field(..., description="文档内容")
    status: DocumentProcessStatus = Field(..., description="处理状态")

# 创建路由
router = APIRouter(
    prefix="/api/docs/processor",
    tags=["document_processor"],
    dependencies=[],
    responses={404: {"description": "Not found"}},
)

@router.post(
    "/process",
    response_model=DocumentProcessResponse,
    operation_id="process_document",
    methods=[HttpMethod.POST],
    summary="处理文档",
    description="从URL或路径处理文档，异步返回文档ID"
)
async def process_document(
    request: DocumentProcessRequest,
    background_tasks: BackgroundTasks,
    token_claims: TokenClaims = Depends(require_user()),
    processor: DocumentProcessor = Depends(get_document_processor),
):
    """处理文档
    
    从URL或路径处理文档，返回文档ID和初始状态。处理会在后台异步进行。
    """
    if not DOCLING_AVAILABLE:
        raise HTTPException(status_code=501, detail="docling未安装，无法使用文档处理功能")
        
    try:
        user_id = token_claims["user_id"]
        doc_id, status = await processor.process_document(
            user_id=user_id,
            source_path=request.source_path,
            doc_id=request.doc_id
        )
        
        return DocumentProcessResponse(
            doc_id=doc_id,
            status=status
        )
    except Exception as e:
        logger.exception(f"处理文档失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理文档失败: {str(e)}")

@router.post(
    "/upload",
    response_model=DocumentProcessResponse,
    operation_id="upload_and_process_document",
    methods=[HttpMethod.POST],
    summary="上传并处理文档",
    description="上传文件并处理，异步返回文档ID"
)
async def upload_and_process_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    doc_id: Optional[str] = Form(None),
    token_claims: TokenClaims = Depends(require_user()),
    processor: DocumentProcessor = Depends(get_document_processor),
    file_service: UploadService = Depends(get_file_service),
):
    """上传并处理文档
    
    上传文件并处理，返回文档ID和初始状态。处理会在后台异步进行。
    """
    if not DOCLING_AVAILABLE:
        raise HTTPException(status_code=501, detail="docling未安装，无法使用文档处理功能")
        
    try:
        user_id = token_claims["user_id"]
        
        # 保存上传的文件
        file_info = await file_service.save_file(user_id, file)
        
        # 处理文档
        doc_id, status = await processor.process_document(
            user_id=user_id,
            source_path=file_info["path"],
            doc_id=doc_id or file_info["id"]
        )
        
        return DocumentProcessResponse(
            doc_id=doc_id,
            status=status
        )
    except Exception as e:
        logger.exception(f"上传并处理文档失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"上传并处理文档失败: {str(e)}")

@router.get(
    "/status/{doc_id}",
    response_model=DocumentProcessStatus,
    operation_id="get_document_process_status",
    methods=[HttpMethod.GET],
    summary="获取文档处理状态",
    description="获取文档处理状态"
)
async def get_document_process_status(
    doc_id: str,
    token_claims: TokenClaims = Depends(require_user()),
    processor: DocumentProcessor = Depends(get_document_processor),
):
    """获取文档处理状态"""
    user_id = token_claims["user_id"]
    status = await processor.get_status(user_id, doc_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"找不到文档处理状态: {doc_id}")
    
    return status

@router.delete(
    "/cancel/{doc_id}",
    response_model=Dict[str, Any],
    operation_id="cancel_document_processing",
    methods=[HttpMethod.DELETE],
    summary="取消文档处理",
    description="取消正在进行的文档处理"
)
async def cancel_document_processing(
    doc_id: str,
    token_claims: TokenClaims = Depends(require_user()),
    processor: DocumentProcessor = Depends(get_document_processor),
):
    """取消文档处理"""
    user_id = token_claims["user_id"]
    cancelled = await processor.cancel_processing(user_id, doc_id)
    
    if not cancelled:
        raise HTTPException(status_code=400, detail=f"无法取消文档处理: {doc_id}")
    
    return {"success": True, "message": f"已取消文档处理: {doc_id}"}

@router.get(
    "/content/{doc_id}",
    response_model=DocumentContentResponse,
    operation_id="get_document_content",
    methods=[HttpMethod.GET],
    summary="获取文档内容",
    description="获取处理后的文档内容"
)
async def get_document_content(
    doc_id: str,
    token_claims: TokenClaims = Depends(require_user()),
    processor: DocumentProcessor = Depends(get_document_processor),
):
    """获取文档内容"""
    user_id = token_claims["user_id"]
    
    # 获取状态
    status = await processor.get_status(user_id, doc_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"找不到文档: {doc_id}")
    
    # 检查是否处理完成
    if status.stage != DocumentProcessStage.COMPLETED:
        raise HTTPException(status_code=400, detail=f"文档尚未处理完成，当前状态: {status.stage}")
    
    # 获取内容
    content = await processor.get_document_content(user_id, doc_id)
    if not content:
        raise HTTPException(status_code=404, detail=f"找不到文档内容: {doc_id}")
    
    return DocumentContentResponse(
        doc_id=doc_id,
        content=content,
        status=status
    )

@router.get(
    "/list",
    response_model=List[DocumentProcessStatus],
    operation_id="list_processing_documents",
    methods=[HttpMethod.GET],
    summary="列出处理中的文档",
    description="列出用户所有处理中的文档"
)
async def list_processing_documents(
    token_claims: TokenClaims = Depends(require_user()),
    processor: DocumentProcessor = Depends(get_document_processor),
):
    """列出处理中的文档"""
    user_id = token_claims["user_id"]
    return await processor.list_processing_documents(user_id) 