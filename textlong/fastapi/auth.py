from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from datetime import datetime, timedelta
from typing import Dict

from ..config import get_default_env

SECRET_KEY = get_default_env("FASTAPI_SECRET_KEY")
ALGORITHM = get_default_env("FASTAPI_ALGORITHM")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_jwt(token: str):
    # 检查token是否以"Bearer "开头，并相应地处理
    if token.lower().startswith("bearer "):
        token = token[7:]  # 去除"Bearer "前缀

    try:
        # 尝试解码token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError as e:
        # 如果解码失败，抛出HTTP异常
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=7)  # 刷新令牌有效期7天
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def default_auth_func(username: str, password: str):
    return {"username": username}

# 存储黑名单令牌
class AuthAPI():
    """
    用户验证。

    Example:
    ```
    app = FastAPI()
    app.include_router(AuthAPI().router)
    ```
    """
    def __init__(self, token_blacklist: set[str]=None, auth_func: callable=None):
        self.token_blacklist = token_blacklist or set()
        self.auth_func = auth_func or default_auth_func

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
                new_access_token = create_access_token(data={"sub": username})
                return {"access_token": new_access_token, "token_type": "bearer"}
            except JWTError:
                raise HTTPException(status_code=403, detail="Token is expired or invalid")

        @router.post("/token")
        async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
            user = self.auth_func(form_data.username, form_data.password)
            if not user:
                raise HTTPException(
                    status_code=400,
                    detail="Incorrect username or password"
                )
            access_token = create_access_token(data={"sub": user['username']})
            refresh_token = create_refresh_token(data={"sub": user['username']})
            return {"access_token": access_token, "token_type": "bearer", "refresh_token": refresh_token}

        @router.get("/users/me")
        async def read_users_me(current_user: dict = Depends(self.get_current_user)):
            return current_user

        @router.get("/protected-route")
        async def protected_route(current_user: dict = Depends(self.get_current_user)):
            return {"message": "This is a protected route", "user": current_user}
        
        self.router = router
    
    def blacklist_add(self, token: str):
        """将Token加入黑名单"""
        self.token_blacklist.add(token)

    def blacklist_discard(self, token: str):
        """从黑名单移除Token"""
        self.token_blacklist.discard(token)

    def is_token_blacklisted(self, token: str) -> bool:
        """判断Token是否在黑名单"""
        return token in self.token_blacklist

    async def get_current_user(self, token: str = Depends(oauth2_scheme)):
        if self.is_token_blacklisted(token):
            raise HTTPException(status_code=403, detail="Token is blacklisted")

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
