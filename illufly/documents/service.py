import os
import shutil
import uuid
import time
import aiofiles
import logging
import mimetypes
import asyncio
import json

from enum import Enum
from typing import List, Dict, Any, Optional, AsyncGenerator, Literal
from pathlib import Path
from fastapi import UploadFile
from voidrail import ClientDealer

from ..llm.retriever.lancedb import LanceRetriever
from .sm import DocumentStateMachine
from .processor import DocumentProcessor
from .meta import DocumentMetaManager
from .events import StateChangedEvent, ResourceActionEvent
from .factory import DocumentMachineFactory
from .events import EventBus

class DocumentStatus(str, Enum):
    """文档状态枚举"""
    ACTIVE = "active"      # 活跃状态，可用
    DELETED = "deleted"    # 已删除
    PROCESSING = "processing"  # 处理中（任何处理阶段）

class DocumentService:
    """简化为协调层，主要负责创建状态机和委托处理器执行操作"""
    
    def __init__(
        self, 
        base_dir: str, 
        max_file_size: int = 50 * 1024 * 1024,
        max_total_size_per_user: int = 200 * 1024 * 1024,
        allowed_extensions: List[str] = None,
        voidrail_client = None,
        retriever = None,
        logger = None
    ):
        self.base_dir = Path(base_dir)
        self.max_file_size = max_file_size
        self.max_total_size_per_user = max_total_size_per_user
        
        # 创建核心组件
        self.meta_manager = DocumentMetaManager(base_dir=str(self.base_dir / "meta"))
        self.processor = DocumentProcessor(
            base_dir=str(self.base_dir),
            meta_manager=self.meta_manager,
            max_file_size=max_file_size,
            allowed_extensions=allowed_extensions,
            voidrail_client=voidrail_client,
            retriever=retriever,
            logger=logger
        )

        self.logger = logger or logging.getLogger(__name__)

    # ==== 状态机管理 ====
    
    def create_state_machine(self, user_id: str, document_id: str, topic_path: str = None) -> DocumentStateMachine:
        """创建文档状态机实例"""
        machine = DocumentStateMachine(
            meta_manager=self.meta_manager,
            user_id=user_id,
            document_id=document_id,
            topic_path=topic_path,
            logger=self.logger
        )
        return machine
    
    # ==== 文档管理 - 委托给处理器 ====
    
    async def create_document(self, user_id: str, doc_info: Dict[str, Any], 
                            topic_path: str = None, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """创建文档元数据并设置初始状态 - 业务流程起点"""
        document_id = doc_info["document_id"]
        
        # 创建元数据
        now = int(time.time())
        meta = {
            **doc_info,
            "created_at": now,
            "updated_at": now,
            "status": "active",
            "state": "init",
            "sub_state": "none",
            "has_markdown": False,
            "has_chunks": False, 
            "has_embeddings": False,
            "has_qa_pairs": False
        }
        
        # 合并用户元数据
        if metadata:
            # 过滤保留字段
            for key in ["document_id", "created_at", "status", "state"]:
                if key in metadata:
                    del metadata[key]
            meta.update(metadata)
        
        # 保存元数据
        doc_meta = await self.meta_manager.create_document(
            user_id, topic_path, doc_info["document_id"], meta
        )
        
        # 创建状态机并设置相应初始状态
        machine = self.create_state_machine(user_id, document_id, topic_path)
        
        # 根据文档类型设置初始状态
        if doc_info.get("source_type") == "remote":
            await machine.set_state("bookmarked", sub_state="completed")
        elif doc_info.get("source_type") == "chat":
            await machine.set_state("saved_chat", sub_state="completed")
        else:
            await machine.set_state("uploaded", sub_state="completed")
            
        return doc_meta
        
    async def upload_document(self, user_id: str, file: UploadFile, topic_path: str = None, 
                            metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """上传文档 - 协调文件处理和状态管理"""
        # 1. 处理文件上传
        file_info = await self.processor.save_and_get_file_info(
            user_id, file, max_total_size=self.max_total_size_per_user
        )
        
        # 2. 创建文档元数据和设置状态
        return await self.create_document(user_id, file_info, topic_path, metadata)
    
    async def create_bookmark(self, user_id: str, url: str, filename: str, 
                            topic_path: str = None, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """创建网络书签文档 - 协调文档注册和状态管理"""
        # 1. 注册远程文档
        doc_info = await self.processor.register_remote_doc_info(user_id, url, filename)
        
        # 2. 创建文档元数据和设置状态
        return await self.create_document(user_id, doc_info, topic_path, metadata)
    
    async def convert_to_markdown(self, user_id: str, document_id: str, topic_path: str = None) -> Dict[str, Any]:
        """转换为Markdown - 协调处理器和状态机"""
        # 1. 创建状态机
        machine = self.create_state_machine(user_id, document_id, topic_path)
        
        # 2. 检查当前状态
        current_state = await machine.get_current_state()
        if current_state not in ["uploaded", "bookmarked"]:
            raise ValueError(f"当前状态 {current_state} 不支持转换为Markdown")
            
        try:
            # 3. 开始处理 - 状态机更新子状态
            await machine.start_processing("markdowned")
            
            # 4. 执行文件处理 - 处理器负责
            result = await self.processor.convert_document_to_markdown(user_id, document_id)
            
            # 5. 完成处理 - 状态机更新状态
            await machine.complete_processing("markdowned")
            
            return {
                **result,
                "document_id": document_id,
                "state": "markdowned",
                "sub_state": "completed"
            }
        except Exception as e:
            # 处理失败 - 状态机记录失败状态
            await machine.fail_processing("markdowned", str(e))
            raise
    
    async def chunk_document(self, user_id: str, document_id: str, topic_path: str = None) -> Dict[str, Any]:
        """将文档切分为片段 - 协调处理器和状态机"""
        # 1. 创建状态机
        machine = self.create_state_machine(user_id, document_id, topic_path)
        
        # 2. 检查当前状态
        current_state = await machine.get_current_state()
        if current_state != "markdowned":
            raise ValueError(f"当前状态 {current_state} 不支持切片")
            
        try:
            # 3. 开始处理 - 状态机负责状态变更
            await machine.start_processing("chunked")
            
            # 4. 执行切片 - 处理器负责文件操作
            result = await self.processor.process_document_chunks(user_id, document_id)
            
            # 5. 更新元数据中的切片信息 - 处理器负责处理相关元数据
            await self.processor.add_chunks_metadata(user_id, document_id, topic_path, result["chunks"])
            
            # 6. 完成处理 - 状态机负责状态变更
            await machine.complete_processing("chunked")
            
            return {
                **result,
                "document_id": document_id,
                "state": "chunked",
                "sub_state": "completed"
            }
        except Exception as e:
            # 处理失败 - 状态机负责状态变更
            await machine.fail_processing("chunked", str(e))
            raise
    
    async def generate_embeddings(self, user_id: str, document_id: str, topic_path: str = None) -> Dict[str, Any]:
        """为文档切片生成向量嵌入"""
        return await self.processor.process_embeddings(
            user_id, document_id, topic_path,
            create_sm_func=self.create_state_machine
        )
    
    async def rollback_to_previous_state(self, user_id: str, document_id: str, topic_path: str = None) -> Dict[str, Any]:
        """回滚到上一个状态 - 协调处理器和状态机"""
        # 1. 创建状态机
        machine = self.create_state_machine(user_id, document_id, topic_path)
        
        # 2. 获取当前状态和前一个状态
        current_state = await machine.get_current_state()
        prev_state = machine.get_previous_state()
        
        if not prev_state:
            raise ValueError(f"当前状态 {current_state} 没有前一个状态可回滚")
            
        # 3. 执行资源回滚操作
        if current_state == "markdowned" and prev_state in ["uploaded", "bookmarked"]:
            # 回滚Markdown，删除MD文件
            await self.processor.remove_markdown_file(user_id, document_id)
        elif current_state == "chunked" and prev_state == "markdowned":
            # 回滚切片，删除切片目录
            await self.processor.remove_chunks_dir(user_id, document_id)
        elif current_state == "embedded" and prev_state in ["chunked", "qa_extracted"]:
            # 回滚嵌入，从向量存储中删除
            await self.processor.remove_vector_embeddings(user_id, document_id)
                
        # 4. 执行状态回滚 - 使用状态机
        await machine.rollback_to_previous(details={"rollback_from": current_state})
        
        # 5. 获取更新后的元数据
        return await self.get_document(user_id, document_id, topic_path)
    
    async def delete_document(self, user_id: str, document_id: str, topic_path: str = None) -> bool:
        """删除文档 - 协调状态管理和资源清理"""
        # 1. 创建状态机
        machine = self.create_state_machine(user_id, document_id, topic_path)
        
        # 2. 更新状态为删除
        deleted = await machine.delete_document_state()
        
        if deleted:
            # 3. 删除文件资源 - 处理器负责
            await self.processor.remove_document_files(user_id, document_id)
            
            # 4. 从向量存储中删除 - 处理器负责
            await self.processor.remove_vector_embeddings(user_id, document_id)
            
            # 5. 完成删除元数据 - 服务层协调
            await self.meta_manager.delete_document(user_id, topic_path, document_id)
        
        return deleted
    
    async def search_documents(self, user_id: str, query: str, document_id: str = None, limit: int = 10) -> List[Dict[str, Any]]:
        """搜索文档内容"""
        return await self.processor.search_document_content(user_id, query, document_id, limit)
    
    async def get_document(self, user_id: str, document_id: str, topic_path: str = None) -> Optional[Dict[str, Any]]:
        """获取文档元数据"""
        return await self.meta_manager.get_metadata(user_id, topic_path, document_id)
    
    async def list_documents(self, user_id: str, topic_path: str = None) -> List[Dict[str, Any]]:
        """列出用户的所有文档"""
        # 使用元数据管理器获取文档列表
        docs = []
        
        if topic_path:
            # 列出特定主题下的文档
            doc_ids = await self.meta_manager.get_document_ids(user_id, topic_path)
            for doc_id in doc_ids:
                doc = await self.meta_manager.get_metadata(user_id, topic_path, doc_id)
                if doc and doc.get("status") == "active":
                    docs.append(doc)
        else:
            # 列出所有文档
            docs = await self.meta_manager.list_all_documents(user_id)
            docs = [doc for doc in docs if doc.get("status") == "active"]
        
        # 按创建时间排序
        docs.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return docs
    
    async def get_document_state(self, user_id: str, document_id: str, topic_path: str = None) -> Dict[str, str]:
        """获取文档当前状态，包括主状态和子状态"""
        machine = self.create_state_machine(user_id, document_id, topic_path)
        return await machine.get_current_state_info()

