from fastapi import FastAPI, Depends, Response, HTTPException, status, Request
from typing import Dict, Any, List, Optional, Callable, Union, Tuple
from pydantic import BaseModel, EmailStr, Field
import uuid
import logging
from datetime import datetime
from enum import Enum

from ...rocksdb import IndexedRocksDB
from ...mq.service import ClientDealer
from ..models import Result, HttpMethod
from ..auth import require_user, TokensManager, TokenClaims
from ..models import Result

def create_chat_endpoints(
    app: FastAPI,
    zmq_client: ClientDealer = None,
    tokens_manager: TokensManager = None,
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

    async def all_threads(
        token_claims: TokenClaims = Depends(require_user(tokens_manager, logger=logger))
    ):
        try:
            results = []
            threads = await zmq_client.invoke("threadmanagerdealer.all_threads", user_id=token_claims['user_id'], timeout=2.0)
            return Result.ok(data=threads[0])

        except HTTPException as e:
            raise e
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e)
            )

    return [
        (HttpMethod.GET, f"{prefix}/chat/threads", all_threads),
    ]
