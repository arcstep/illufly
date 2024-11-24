from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, Request, Response
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

async def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # 检查令牌是否在白名单中
        if not is_access_token_in_whitelist(token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token not in whitelist",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 使用 verify_jwt 方法验证 JWT 并获取 payload
        username: str = verify_jwt(token)
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

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
    async def refresh_token(request: Request):
        # 从 Cookies 中获取 refresh_token
        refresh_token = request.cookies.get("refresh_token")
        if not refresh_token or not is_refresh_token_in_whitelist(refresh_token):
            raise HTTPException(status_code=403, detail="Refresh token is not in whitelist")
        try:
            payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username is None:
                raise HTTPException(status_code=400, detail="Invalid refresh token")
            new_access_token = _create_access_token(data={"sub": username})
            
            # 设置新的 access_token 到 HttpOnly Cookie
            response = Response()
            response.set_cookie(
                key="access_token",
                value=new_access_token,
                httponly=True,
                secure=True,  # 在生产环境中使用 HTTPS 时设置为 True
                samesite="Lax"  # 或者 "Strict" 根据需求
            )
            
            return {"access_token": new_access_token, "token_type": "bearer"}
        except JWTError:
            raise HTTPException(status_code=403, detail="Token is expired or invalid")

    @router.post("/login")
    async def login_for_access_token(response: Response, form_data: OAuth2PasswordRequestForm = Depends()):
        user_info = auth_func(form_data.username, form_data.password)
        if not user_info:
            raise HTTPException(
                status_code=400,
                detail="Incorrect username or password"
            )
        access_token = _create_access_token(data=user_info)
        refresh_token = _create_refresh_token(data=user_info)

        # 设置 HttpOnly Cookie
        set_auth_cookies(response, access_token, refresh_token)

        return user_info

    @router.post("/logout")
    async def logout(response: Response, current_user: dict = Depends(get_current_user)):
        remove_access_token_from_whitelist(current_user)
        remove_refresh_token_from_whitelist(current_user)
        
        # 清除 cookies
        response.delete_cookie(key="access_token")
        response.delete_cookie(key="refresh_token")
        
        return {"message": "User logged out successfully"}

    @router.get("/profile")
    async def read_user_me(user: dict = Depends(get_current_user)):
        print("user", user)
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

def set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,  # 在生产环境中使用 HTTPS 时设置为 True
        samesite="Lax"  # 或者 "Strict" 根据需求
    )
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,  # 在生产环境中使用 HTTPS 时设置为 True
        samesite="Lax"  # 或者 "Strict" 根据需求
    )

