import uvicorn

# 启动命令
# python -m illufly.fastapi.openai.start
if __name__ == "__main__":
    uvicorn.run("illufly.api.openai.endpoints:app", host="0.0.0.0", port=8000, reload=True)
