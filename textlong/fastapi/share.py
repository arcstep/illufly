import mistune
import os
from ..config import get_folder_share

def create_app():
    from fastapi import FastAPI, HTTPException
    from starlette.responses import HTMLResponse

    """
    ```python
    import uvicorn
    from textlong.fastapi.share import create_app

    app = create_app()

    if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
    ```
    """
    app = FastAPI()

    HTML_DIR = get_folder_share()

    @app.post("/publish/{id}")
    async def publish(id: str, md: str):
        markdown = mistune.create_markdown()
        html = markdown(md)
        file_path = os.path.join(HTML_DIR, f'{id}.html')
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, "w") as f:
            f.write(html)

        return {"message": "HTML published successfully"}

    @app.get("/publish/{id}", response_class=HTMLResponse)
    async def get_html(id: str):
        file_path = os.path.join(HTML_DIR, f"{id}.html")
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="HTML not found")

        with open(file_path, "r") as f:
            return f.read()
    
    return app
