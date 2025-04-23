from fastapi import FastAPI, Depends, Response, HTTPException, status, Query
from typing import Dict, Any, List, Optional, Callable, Union, Tuple
from pydantic import BaseModel, Field

import logging
import json

from soulseal import TokenSDK
from ..schemas import Result, HttpMethod
from ..http import handle_errors
from ...agents import ChatAgent, MemoryQA
from ...envir import get_env

class MemoryUpdateRequest(BaseModel):
    topic: Optional[str] = Field(default=None, description="记忆主题")
    question: Optional[str] = Field(default=None, description="记忆问题")
    answer: Optional[str] = Field(default=None, description="记忆答案")

class MemorySearchRequest(BaseModel):
    query: str = Field(..., description="搜索查询")
    threshold: float = Field(default=1.5, description="距离阈值，0-2范围，越小越相似")
    top_k: int = Field(default=15, description="返回结果数量")

def create_memory_endpoints(
    app: FastAPI,
    token_sdk: TokenSDK,
    agent: ChatAgent,
    prefix: str="/api",
    logger: logging.Logger = None
) -> List[Tuple[HttpMethod, str, Callable]]:
    """创建记忆管理相关的API端点
    
    Returns:
        List[Tuple[HttpMethod, str, Callable]]: 
            元组列表 (HTTP方法, 路由路径, 处理函数)
    """

    logger = logging.getLogger(__name__)
    require_user = token_sdk.get_auth_dependency(logger=logger)

    @handle_errors()
    async def all_memory(
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """获取所有记忆"""
        return agent.memory.all_memory(token_claims['user_id'])

    @handle_errors()
    async def update_memory(
        memory_id: str,
        memory_data: MemoryUpdateRequest,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """更新指定记忆"""
        try:
            # 尝试获取原始记忆
            user_id = token_claims['user_id']
            memory_key = MemoryQA.get_key(user_id, memory_id)
            original_memory = agent.memory.memory_db.get_as_model(MemoryQA.__name__, memory_key)
                    
            if not original_memory:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"未找到记忆: {memory_id}")
            
            # 只更新用户提供的字段
            update_topic = memory_data.topic if memory_data.topic is not None else original_memory.topic
            update_question = memory_data.question if memory_data.question is not None else original_memory.question
            update_answer = memory_data.answer if memory_data.answer is not None else original_memory.answer
            
            # 调用update_memory方法更新记忆
            updated_memory = await agent.memory.update_memory(
                user_id=user_id,
                memory_id=memory_id,
                topic=update_topic,
                question=update_question,
                answer=update_answer
            )
            return updated_memory
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        except Exception as e:
            logger.error(f"更新记忆失败: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"更新记忆失败: {str(e)}")

    @handle_errors()
    async def delete_memory(
        memory_id: str,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """删除指定记忆"""
        try:
            success = await agent.memory.delete_memory(
                user_id=token_claims['user_id'],
                memory_id=memory_id
            )
            if success:
                return {"success": True, "message": "记忆删除成功"}
            else:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"未找到记忆: {memory_id}")
        except Exception as e:
            logger.error(f"删除记忆失败: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"删除记忆失败: {str(e)}")

    @handle_errors()
    async def search_memory(
        search_request: MemorySearchRequest,
        token_claims: Dict[str, Any] = Depends(require_user)
    ):
        """搜索记忆"""
        try:
            results = await agent.memory.retrieve(
                input_messages=search_request.query,
                user_id=token_claims['user_id'],
                threshold=search_request.threshold,
                top_k=search_request.top_k
            )
            return results
        except Exception as e:
            logger.error(f"搜索记忆失败: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"搜索记忆失败: {str(e)}")

    return [
        (HttpMethod.GET, f"{prefix}/memory", all_memory),
        (HttpMethod.PUT, f"{prefix}/memory/{{memory_id}}", update_memory),
        (HttpMethod.DELETE, f"{prefix}/memory/{{memory_id}}", delete_memory),
        (HttpMethod.POST, f"{prefix}/memory/search", search_memory),
    ] 