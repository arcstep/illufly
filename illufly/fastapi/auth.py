from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, Request, Response
from jose import jwt, JWTError
from datetime import datetime, timedelta
from typing import Dict
from fastapi.security import OAuth2PasswordRequestForm

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

async def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        print("没有 token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    try:
        if not is_access_token_in_whitelist(token):
            print("token 不在白名单中")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token not in whitelist"
            )

        username: str = verify_jwt(token)
        if username is None:
            print("token 无效")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
    except JWTError:
        print("token 解码失败")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )

    return {"username": username}

def create_auth_endpoints(app, auth_func: callable=None, prefix: str="/api"):
    """
    用户验证。

    Example:
    ```
    app = FastAPI()
    create_auth_endpoints(app)
    ```
    """
    auth_func = auth_func or default_auth_func

    router = APIRouter()

    @app.post(f"{prefix}/auth/refresh-token")
    async def refresh_token(request: Request, response: Response):
        refresh_token = request.cookies.get("refresh_token")
        if not refresh_token or not is_refresh_token_in_whitelist(refresh_token):
            raise HTTPException(status_code=403, detail="Refresh token is not in whitelist")
        try:
            username: str = verify_jwt(refresh_token)
            if username is None:
                raise HTTPException(status_code=400, detail="Invalid refresh token")
            new_access_token = _create_access_token(data={"username": username})            
            set_auth_cookies(response, access_token=new_access_token)
            
            return {"message": "Access token refreshed successfully"}

        except JWTError:
            raise HTTPException(status_code=403, detail="Token is expired or invalid")

    @app.post(f"{prefix}/auth/remove-access-token")
    async def remove_access_token(request: Request):
        username = verify_jwt(request.cookies.get("access_token"))
        remove_access_token_from_whitelist(username)
        return {"message": "Access token removed successfully"}

    @app.post(f"{prefix}/auth/remove-refresh-token")
    async def remove_refresh_token(request: Request):
        username = verify_jwt(request.cookies.get("refresh_token"))
        remove_refresh_token_from_whitelist(username)
        return {"message": "Refresh token removed successfully"}

    @app.post(f"{prefix}/auth/login")
    async def login_for_access_token(response: Response, form_data: OAuth2PasswordRequestForm = Depends()):
        user_info = auth_func(form_data.username, form_data.password)
        if not user_info:
            raise HTTPException(
                status_code=400,
                detail="Incorrect username or password"
            )
        access_token = _create_access_token(data=user_info)
        refresh_token = _create_refresh_token(data=user_info)

        set_auth_cookies(response, access_token, refresh_token)

        return user_info

    @app.post(f"{prefix}/auth/logout")
    async def logout(response: Response, current_user: dict = Depends(get_current_user)):
        remove_access_token_from_whitelist(current_user)
        remove_refresh_token_from_whitelist(current_user)
        
        response.delete_cookie(key="access_token")
        response.delete_cookie(key="refresh_token")
        
        return {"message": "User logged out successfully"}

    @app.get(f"{prefix}/auth/profile")
    async def read_user_me(user: dict = Depends(get_current_user)):
        print("user", user)
        return user
    
    return router

def verify_jwt(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("username")
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        ) from e

def _create_refresh_token(data: dict):
    expire_days = get_env("ACCESS_TOKEN_EXPIRE_DAYS")
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=expire_days)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    add_refresh_token_to_whitelist(encoded_jwt, data.get('username') or data.get('sub'), expire_days)
    return encoded_jwt

def _create_access_token(data: dict):
    expire_minutes = get_env("ACCESS_TOKEN_EXPIRE_MINUTES")
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    add_access_token_to_whitelist(encoded_jwt, data.get('username') or data.get('sub'), expire_minutes)
    return encoded_jwt

def set_auth_cookies(response: Response, access_token: str=None, refresh_token: str=None):
    if access_token:
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=True,
            samesite="Lax"
        )

    if refresh_token:
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=True,
            samesite="Lax"
        )

