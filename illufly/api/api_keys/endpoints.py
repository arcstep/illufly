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
from .api_keys import ApiKeysManager

def create_api_keys_endpoints(
    app: FastAPI,
    tokens_manager: TokensManager = None,
    api_keys_manager: ApiKeysManager = None,
    prefix: str = "/api",
    base_url: str = "/api",
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
        imitator: str = Field(default="OPENAI", description="OpenAI兼容接口的模仿来源")
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
                imitator=api_key_form.imitator,
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
            result = api_keys_manager.list_api_keys(token_claims['user_id'], base_url=base_url)
            if result.is_ok():
                return sorted(result.data, key=lambda x: x['expires_at'], reverse=True)
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

    async def revoke_api_key(
        api_key: str,
        response: Response,
        token_claims: TokenClaims = Depends(require_user(tokens_manager, logger=logger))
    ):
        """撤销API密钥"""
        if not api_keys_manager:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="API密钥管理器未初始化"
            )
        try:
            result = api_keys_manager.revoke_api_key(token_claims['user_id'], api_key)
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
        (HttpMethod.POST, f"{prefix}/apikeys", create_api_key),
        (HttpMethod.GET, f"{prefix}/apikeys", list_api_keys),
        (HttpMethod.POST, f"{prefix}/apikeys/revoke/{{api_key}}", revoke_api_key),
    }
