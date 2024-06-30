"""
例子：

```
# file: my/api.py
# shell: poetry run uvicorn my.api:app

from fastapi import FastAPI
from langchain_zhipu import ChatZhipuAI
from textlong.fastapi import create_auth_api, create_project_api

llm = ChatZhipuAI(model="glm-4-flash")

app = FastAPI()
app.include_router(create_auth_api())
app.include_router(create_project_api(llm))
```
"""

from .auth import create_auth_api, get_current_user
from .project import create_project_api