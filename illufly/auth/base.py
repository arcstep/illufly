from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from datetime import datetime, timedelta
from typing import Dict

from .whitelist import (
    is_refresh_token_in_whitelist,
    add_refresh_token_to_whitelist,
    remove_refresh_token_from_whitelist,

    is_access_token_in_whitelist, 
    add_access_token_to_whitelist,
    remove_access_token_from_whitelist,
)
from ..config import get_env

SECRET_KEY = get_env("FASTAPI_SECRET_KEY")
ALGORITHM = get_env("FASTAPI_ALGORITHM")

# 定义tokenUrl
TOKEN_URL = "login"

# 初始化OAuth2PasswordBearer
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=TOKEN_URL)

TOKEN_BLACKLIST = set()


# 修改 refresh_token 和 logout 逻辑，并在生成新的刷新令牌时调用 add_refresh_token_to_whitelist
# 在 refresh_token 逻辑中首先调用 is_refresh_token_in_whitelist 检查令牌是否有效
# 在 logout 逻辑中调用 remove_refresh_token_from_whitelist 移除令牌

def default_auth_func(username: str, password: str):
    """
    默认的用户认证方法，需要自定义并传入给 `create_auth_api`

    例子：

    ```
    from fastapi import FastAPI
    from illufly.auth import create_auth_api

    def custom_auth_func(username: str, password: str):
        # 这里可以添加自定义的认证逻辑
        return {"username": username}

    app = FastAPI()
    app.include_router(create_auth_api(custom_auth_func))
    ```
    """
    return {"username": username}

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """从JWT中解析当前用户"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=f"Could not validate credentials. Please obtain a valid token from {TOKEN_URL}",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # 检查令牌是否在白名单中
        if not is_access_token_in_whitelist(token):
            raise credentials_exception

        # 使用 verify_jwt 方法验证 JWT 并获取 payload
        username: str = verify_jwt(token)
        if username is None:
            raise credentials_exception
    except JWTError:
        # 捕获JWT解码错误并抛出自定义异常
        raise credentials_exception
    except HTTPException as e:
        # 直接抛出 verify_jwt 中可能产生的异常
        raise e

    return {"username": username}

def create_auth_api(auth_func: callable=None):
    """
    用户验证。

    Example:
    ```
    app = FastAPI()
    app.include_router(AuthAPI().router)
    ```
    """
    auth_func = auth_func or default_auth_func

    router = APIRouter()

    @router.post("/token/refresh")
    async def refresh_token(refresh_token: str):
        # 检查刷新令牌是否在白名单中
        if not is_refresh_token_in_whitelist(refresh_token):
            raise HTTPException(status_code=403, detail="Refresh token is not in whitelist")
        try:
            payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username is None:
                raise HTTPException(status_code=400, detail="Invalid refresh token")
            new_access_token = _create_access_token(data={"sub": username})
            return {"access_token": new_access_token, "token_type": "bearer"}
        except JWTError:
            raise HTTPException(status_code=403, detail="Token is expired or invalid")

    @router.post("/login")
    async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
        user_info = auth_func(form_data.username, form_data.password)
        if not user_info:
            raise HTTPException(
                status_code=400,
                detail="Incorrect username or password"
            )
        access_token = _create_access_token(data=user_info)
        refresh_token = _create_refresh_token(data=user_info)
        return {
            "token_type": "bearer",
            "access_token": access_token,
            "refresh_token": refresh_token
        }

    @router.post("/logout")
    async def logout(current_user: dict = Depends(get_current_user), token: str = Depends(oauth2_scheme)):
        remove_access_token_from_whitelist(current_user)
        remove_refresh_token_from_whitelist(current_user)
        return {"message": "User logged out successfully"}

    @router.get("/users/me")
    async def read_users_me(user: dict = Depends(get_current_user)):
        return user
    
    return router

def verify_jwt(token: str):
    if token.lower().startswith("bearer "):
        token = token[7:]  # 去除 "Bearer " 前缀

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("username")
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

def _create_refresh_token(data: dict):
    expire_days = 15
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=expire_days)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    add_refresh_token_to_whitelist(encoded_jwt, data['username'], expire_days)
    return encoded_jwt

def _create_access_token(data: dict):
    expire_minutes = 15
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    add_access_token_to_whitelist(encoded_jwt, data['username'], expire_minutes)
    return encoded_jwt

