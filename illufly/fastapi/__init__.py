"""
例子：

```
from fastapi import FastAPI
from illufly.auth import create_auth_api

app = FastAPI()
app.include_router(create_auth_api())
```
"""

from .invite import InviteCodeManager
from .vectordb import VectorDBManager
from .auth import AuthManager, AuthDependencies
from .users import create_user_endpoints, UsersManager
from .agents import create_agent_endpoints, AgentsManager
