from fastapi import FastAPI, Depends, HTTPException, Request
from typing import Dict, Any, List, Optional, Callable, Tuple, Union
from pydantic import BaseModel
import logging
import shutil

from soulseal import TokenSDK
from ..schemas import Result, HttpMethod
from ..http import handle_errors
from ...documents.service import DocumentService
from ...documents.topic import TopicManager

# 主题请求模型
class CreateTopicRequest(BaseModel):
    """创建主题请求"""
    path: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    parent_path: Optional[str] = None

class UpdateTopicRequest(BaseModel):
    """更新主题请求"""
    display_name: Optional[str] = None
    description: Optional[str] = None
    
class MoveTopicRequest(BaseModel):
    """移动主题请求"""
    target_path: str
    overwrite: bool = False

class CopyTopicRequest(BaseModel):
    """复制主题请求"""
    target_path: str
    overwrite: bool = False

class AddDocumentToTopicRequest(BaseModel):
    """添加文档到主题请求"""
    document_ids: List[str]

class SearchTopicRequest(BaseModel):
    """搜索主题请求"""
    keyword: str
    recursive: bool = True

def create_topics_endpoints(
    app: FastAPI,
    token_sdk: TokenSDK,
    document_service: DocumentService,
    prefix: str = "/api",
    logger: logging.Logger = None
) -> List[Tuple[HttpMethod, str, Callable]]:
    """创建主题管理相关的API端点
    
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
    
    # 获取主题管理器
    topic_manager = TopicManager(
        base_dir=document_service.base_dir / "docs",
        meta_manager=document_service.meta_manager  # 传入元数据管理器
    )
    
    @handle_errors()
    async def list_topics(
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """获取用户所有主题"""
        user_id = token_claims["user_id"]
        topics = topic_manager.list_all_topics(user_id)
        
        # 格式化结果
        result = []
        for topic in topics:
            # 获取该主题下的文档数量
            doc_ids = topic_manager.get_document_ids_in_topic(user_id, topic["path"])
            
            result.append({
                "path": topic["path"],
                "name": topic["path"].split("/")[-1] if "/" in topic["path"] else topic["path"],
                "is_root": topic["path"] == "/",
                "document_count": topic["document_count"],
                "subtopic_count": topic["subtopic_count"],
                "full_path": f"/topics/{user_id}/{topic['path']}".replace("//", "/")
            })
            
        return {
            "success": True,
            "count": len(result),
            "topics": result
        }
    
    @handle_errors()
    async def get_topic_details(
        path: str = "",
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """获取特定主题的详细信息"""
        user_id = token_claims["user_id"]
        
        # 清理路径格式
        clean_path = path.strip("/")
        
        # 获取主题结构
        topic_structure = topic_manager.get_topic_structure(user_id, clean_path)
        
        # 获取子主题详情
        subtopics = []
        for subtopic_name in topic_structure["subtopics"]:
            subtopic_path = f"{clean_path}/{subtopic_name}".lstrip("/")
            subtopic_detail = topic_manager.get_topic_structure(user_id, subtopic_path)
            subtopics.append({
                "name": subtopic_name,
                "path": subtopic_path,
                "full_path": f"/topics/{subtopic_path}",
                "document_count": len(subtopic_detail["document_ids"]),
                "subtopic_count": len(subtopic_detail["subtopics"])
            })
        
        # 获取文档ID列表，但不获取详细内容
        document_ids = []
        for doc_dir_name in topic_structure["document_ids"]:
            doc_id = topic_manager.extract_document_id(Path(doc_dir_name))
            if doc_id:
                document_ids.append(doc_id)
                
        return {
            "success": True,
            "path": clean_path,
            "name": clean_path.split("/")[-1] if clean_path else "/",
            "is_root": not clean_path,
            "document_count": len(document_ids),
            "document_ids": document_ids,
            "subtopic_count": len(subtopics),
            "subtopics": subtopics,
            "parent_path": "/".join(clean_path.split("/")[:-1]) if "/" in clean_path else ""
        }
    
    @handle_errors()
    async def create_topic(
        topic_request: CreateTopicRequest,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """创建新的主题目录"""
        user_id = token_claims["user_id"]
        
        # 清理路径格式
        path = topic_request.path.strip("/")
        if not path:
            raise HTTPException(status_code=400, detail="主题路径不能为空")
        
        # 如果指定了父路径，则构建完整路径
        if topic_request.parent_path:
            parent = topic_request.parent_path.strip("/")
            path = f"{parent}/{path}" if parent else path
        
        # 创建主题
        success = topic_manager.create_topic(user_id, path)
        if not success:
            raise HTTPException(status_code=400, detail="创建主题失败")
        
        # 获取创建后的主题详情
        topic_structure = topic_manager.get_topic_structure(user_id, path)
        
        return {
            "success": True,
            "path": path,
            "name": path.split("/")[-1],
            "document_count": 0,
            "subtopic_count": 0,
            "message": "主题创建成功"
        }
    
    @handle_errors()
    async def update_topic(
        path: str,
        topic_request: UpdateTopicRequest,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """更新主题信息"""
        user_id = token_claims["user_id"]
        
        # 清理路径格式
        clean_path = path.strip("/")
        if not clean_path:
            raise HTTPException(status_code=400, detail="无法更新根主题")
        
        # 检查主题是否存在
        topic_path = topic_manager.get_topic_path(user_id, clean_path)
        if not topic_path.exists():
            raise HTTPException(status_code=404, detail="主题不存在")
        
        # 目前只支持重命名
        if topic_request.display_name:
            # 获取父路径和当前名称
            parent_path = "/".join(clean_path.split("/")[:-1])
            new_name = topic_request.display_name
            
            # 执行重命名
            success = topic_manager.rename_topic(user_id, clean_path, new_name)
            if not success:
                raise HTTPException(status_code=400, detail="主题更新失败")
            
            # 构建新路径
            new_path = f"{parent_path}/{new_name}" if parent_path else new_name
            
            return {
                "success": True,
                "old_path": clean_path,
                "new_path": new_path,
                "message": "主题已更新"
            }
        
        return {
            "success": True,
            "path": clean_path,
            "message": "没有变更"
        }
    
    @handle_errors()
    async def delete_topic(
        path: str,
        force: bool = False,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """删除主题"""
        user_id = token_claims["user_id"]
        clean_path = path.strip("/")
        
        if not clean_path:
            raise HTTPException(status_code=400, detail="无法删除根主题")
        
        # 验证主题存在
        if not topic_manager.get_topic_path(user_id, clean_path).exists():
            raise HTTPException(status_code=404, detail="主题不存在")
        
        # 执行删除 - 使用异步方法
        success = await topic_manager.delete_topic(user_id, clean_path, force)
        if not success:
            raise HTTPException(status_code=400, detail="删除主题失败")
        
        return {
            "success": True,
            "path": clean_path,
            "message": "主题已删除"
        }
    
    @handle_errors()
    async def move_topic(
        path: str,
        move_request: MoveTopicRequest,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """移动主题到新位置"""
        user_id = token_claims["user_id"]
        
        # 清理路径格式
        source_path = path.strip("/")
        target_path = move_request.target_path.strip("/")
        
        if not source_path:
            raise HTTPException(status_code=400, detail="无法移动根主题")
            
        # 验证源主题存在
        if not topic_manager.get_topic_path(user_id, source_path).exists():
            raise HTTPException(status_code=404, detail="源主题不存在")
        
        # 执行移动
        success = topic_manager.move_topic(user_id, source_path, target_path)
        if not success:
            raise HTTPException(status_code=400, detail="移动主题失败")
        
        # 构造新路径
        source_name = source_path.split("/")[-1]
        new_path = f"{target_path}/{source_name}" if target_path else source_name
        
        return {
            "success": True,
            "old_path": source_path,
            "new_path": new_path,
            "message": "主题已移动"
        }
    
    @handle_errors()
    async def search_topics(
        request: SearchTopicRequest,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """搜索主题"""
        user_id = token_claims["user_id"]
        
        # 执行搜索
        matched_topics = topic_manager.search_topics(user_id, request.keyword)
        
        # 格式化结果
        result = []
        for topic in matched_topics:
            result.append({
                "path": topic["path"],
                "name": topic["path"].split("/")[-1] if "/" in topic["path"] else topic["path"],
                "is_root": topic["path"] == "/",
                "document_count": topic["document_count"],
                "subtopic_count": topic["subtopic_count"],
                "full_path": f"/topics/{user_id}/{topic['path']}".replace("//", "/")
            })
        
        return {
            "success": True,
            "keyword": request.keyword,
            "count": len(result),
            "topics": result
        }
    
    @handle_errors()
    async def get_topic_documents(
        path: str,
        recursive: bool = False,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """获取主题中的所有文档，支持递归获取子主题文档"""
        user_id = token_claims["user_id"]
        
        # 清理路径格式
        clean_path = path.strip("/")
        
        # 获取主题中的文档ID（支持递归）
        document_ids = await topic_manager.get_all_documents_in_topic(user_id, clean_path, recursive)
        
        # 获取文档详情
        documents = []
        for doc_id in document_ids:
            doc = await document_service.get_document(user_id, doc_id)
            if doc:
                documents.append({
                    "document_id": doc_id,
                    "title": doc.get("title", ""),
                    "original_name": doc.get("original_name", ""),
                    "type": doc.get("type", ""),
                    "extension": doc.get("extension", ""),
                    "created_at": doc.get("created_at", 0),
                    "has_markdown": doc.get("has_markdown", False),
                    "state": doc.get("state", "init"),
                    "topic_path": doc.get("topic_path", "")  # 添加主题路径，便于确定文档位置
                })
        
        return {
            "success": True,
            "path": clean_path,
            "recursive": recursive,
            "count": len(documents),
            "documents": documents
        }
    
    # 返回路由列表
    return [
        (HttpMethod.GET, f"{prefix}/topics", list_topics),
        (HttpMethod.GET, f"{prefix}/topics/{{path:path}}", get_topic_details),
        (HttpMethod.POST, f"{prefix}/topics", create_topic),
        (HttpMethod.PUT, f"{prefix}/topics/{{path:path}}", update_topic),
        (HttpMethod.DELETE, f"{prefix}/topics/{{path:path}}", delete_topic),
        (HttpMethod.POST, f"{prefix}/topics/{{path:path}}/move", move_topic),
        (HttpMethod.GET, f"{prefix}/topics/{{path:path}}/documents", get_topic_documents),
        (HttpMethod.POST, f"{prefix}/topics/search", search_topics),
    ]
