from fastapi import FastAPI, Depends, Response, HTTPException, status, Request
from typing import Dict, Any, List, Optional, Callable, Union, Tuple
from pydantic import BaseModel, EmailStr, Field
import uuid
import logging
from datetime import datetime
from enum import Enum

from ...rocksdb import IndexedRocksDB
from ..models import Result, HttpMethod
from ..auth import require_user, TokensManager, TokenClaims
from .chats import ChatsManager

def create_chats_endpoints(
    app: FastAPI,
    tokens_manager: TokensManager = None,
    chats_manager: ChatsManager = None,
    prefix: str="/api",
    logger: logging.Logger = None
) -> Dict[str, Tuple[HttpMethod, str, Callable]]:
    """创建认证相关的API端点
    
    Returns:
        Dict[str, Tuple[HttpMethod, str, Callable]]: 
            键为路由名称，
            值为元组 (HTTP方法, 路由路径, 处理函数)
    """

    logger = logger or logging.getLogger(__name__)

    class CreateApiKeyRequest(BaseModel):
        """创建API密钥请求"""
        description: str = Field(default=None, description="API密钥描述")

    async def create_api_key(
        api_key_form: CreateApiKeyRequest,
        response: Response,
        token_claims: TokenClaims = Depends(require_user(tokens_manager, logger=logger))
    ):
        """创建API密钥"""
        if not api_keys_manager:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="API密钥管理器未初始化"
            )
        try:
            result = api_keys_manager.create_api_key(
                user_id=token_claims['user_id'],
                description=api_key_form.description
            )
            logger.info(f"创建 API 密钥结果: {result.data}")
            if result.is_ok():
                return result
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=result.error
                )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )
        
    async def list_api_keys(
        token_claims: TokenClaims = Depends(require_user(tokens_manager, logger=logger))
    ):
        """列出API密钥"""
        if not api_keys_manager:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="API密钥管理器未初始化"
            )
        try:
            result = api_keys_manager.list_api_keys(token_claims['user_id'])
            if result.is_ok():
                return result
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=result.error
                )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )

    async def delete_api_key(
        api_key: str,
        response: Response,
        token_claims: TokenClaims = Depends(require_user(tokens_manager, logger=logger))
    ):
        """删除API密钥"""
        if not api_keys_manager:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="API密钥管理器未初始化"
            )
        try:
            result = api_keys_manager.delete_api_key(token_claims['user_id'], api_key)
            if result.is_ok():
                return result
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=result.error
                )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )

    return {
        "create_api_key": (HttpMethod.POST, f"{prefix}/auth/api-keys", create_api_key),
        "list_api_keys": (HttpMethod.GET, f"{prefix}/auth/api-keys", list_api_keys),
        "delete_api_key": (HttpMethod.DELETE, f"{prefix}/auth/api-keys/{{api_key}}", delete_api_key),
    }
