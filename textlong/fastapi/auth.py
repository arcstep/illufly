from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from datetime import datetime, timedelta
from typing import Dict

from ..config import get_default_env

SECRET_KEY = get_default_env("FASTAPI_SECRET_KEY")
ALGORITHM = get_default_env("FASTAPI_ALGORITHM")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def default_auth_func(username: str, password: str):
    """默认的用户认证方法"""
    return {"username": username}

def is_token_blacklisted(token: str) -> bool:
    """判断Token是否在黑名单"""
    return token in set()

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """从JWT中解析当前用户"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # 使用verify_jwt方法验证JWT并获取payload
        username: str = verify_jwt(token)
        if username is None:
            raise credentials_exception
    except HTTPException as e:
        # 直接抛出verify_jwt中可能产生的异常
        raise e
    return {"username": username}

def create_auth_api(auth_func: callable=None, is_token_blacklisted: callable=None):
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
        if is_token_blacklisted(refresh_token):
            raise HTTPException(status_code=403, detail="Token is blacklisted")
        try:
            payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username is None:
                raise HTTPException(status_code=400, detail="Invalid refresh token")
            new_access_token = _create_access_token(data={"sub": username})
            return {"access_token": new_access_token, "token_type": "bearer"}
        except JWTError:
            raise HTTPException(status_code=403, detail="Token is expired or invalid")

    @router.post("/token")
    async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
        user = auth_func(form_data.username, form_data.password)
        if not user:
            raise HTTPException(
                status_code=400,
                detail="Incorrect username or password"
            )
        access_token = _create_access_token(data={"sub": user['username']})
        refresh_token = _create_refresh_token(data={"sub": user['username']})
        return {"access_token": access_token, "token_type": "bearer", "refresh_token": refresh_token}

    @router.get("/users/me")
    async def read_users_me(user: dict = Depends(get_current_user)):
        return user

    @router.get("/protected-route")
    async def protected_route(user: dict = Depends(get_current_user)):
        return {"message": "This is a protected route", "user": user}
    
    return router

def verify_jwt(token: str):
    if token.lower().startswith("bearer "):
        token = token[7:]  # 去除"Bearer "前缀

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

def _create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=7)  # 刷新令牌有效期7天
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def _create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

