"""
例子：

```
from fastapi import FastAPI
from illufly.auth import create_auth_api

app = FastAPI()
app.include_router(create_auth_api())
```
"""

from .auth import AuthManager, AuthDependencies
from .user import create_user_endpoints, UserManager
from .agent import create_agent_endpoints, AgentManager
