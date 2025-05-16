import pytest
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient
import tempfile
import shutil
import os
import time
import json
import io
from pathlib import Path

from soulseal import TokenSDK
from soulseal.tokens.token_schemas import JWT_SECRET_KEY, JWT_ALGORITHM
from illufly.documents.service import DocumentService
from illufly.api.endpoints.documents import create_documents_endpoints
from illufly.api.schemas import HttpMethod


@pytest.fixture
def temp_dir():
    """创建临时目录用于测试"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def doc_service(temp_dir):
    """创建文档服务实例，使用真实的数据库和处理器"""
    service = DocumentService(
        base_dir=temp_dir,
        max_file_size=5 * 1024 * 1024,  # 5MB限制
        max_total_size_per_user=20 * 1024 * 1024,  # 20MB总限制
        embedding_config={}
    )
    return service


@pytest.fixture
def token_sdk(temp_dir):
    """创建真实的令牌SDK实例"""
    db_path = os.path.join(temp_dir, "tokens_db")
    os.makedirs(db_path, exist_ok=True)
    
    # 使用临时目录中的数据库
    from voidring import IndexedRocksDB
    db = IndexedRocksDB(db_path)
    return TokenSDK(db=db)


@pytest.fixture
def test_user():
    """测试用户数据"""
    return {
        "user_id": "test_user_id",
        "username": "testuser",
        "roles": ["user"]
    }


@pytest.fixture
def test_app(doc_service, token_sdk):
    """创建测试应用"""
    app = FastAPI()
    
    # 创建文档API端点
    doc_handlers = create_documents_endpoints(
        app=app,
        token_sdk=token_sdk,
        document_service=doc_service,
        prefix="/api"
    )
    
    # 注册端点到应用
    for method, path, handler in doc_handlers:
        app.add_api_route(
            path=path,
            endpoint=handler,
            methods=[method.value],
            response_model=None,
        )
    
    return app


@pytest.fixture
def auth_token(test_user):
    """创建有效的认证令牌"""
    import jwt
    import time
    
    # 创建标准格式的JWT令牌
    payload = {
        **test_user,
        "exp": time.time() + 3600,  # 令牌过期时间
        "iat": time.time(),          # 令牌签发时间
        "device_id": "test_device"
    }
    
    # 使用标准密钥和算法创建令牌
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


@pytest.fixture
def client(test_app, auth_token):
    """创建测试客户端"""
    client = TestClient(test_app)
    client.headers = {"Authorization": f"Bearer {auth_token}"}
    return client


@pytest.fixture
def sample_text_file(temp_dir):
    """创建样本文本文件"""
    file_path = Path(temp_dir) / "sample.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("这是一个测试文本文件\n这是第二行内容\n这是第三行内容")
    return file_path


@pytest.fixture
async def my_upload_document(client, sample_text_file):
    """上传文档并返回文档ID的fixture"""
    async def _upload_document():
        # 直接使用样本文件，不再使用upload_file fixture
        with open(sample_text_file, "rb") as f:
            response = client.post(
                "/api/documents/upload",
                files={"file": ("sample.txt", f, "text/plain")},
                data={"title": "测试文档", "description": "这是一个测试文档"}
            )
        
        # 验证响应
        assert response.status_code == 200
        result = response.json()
        
        # 验证结果包含预期的数据
        assert result["success"] is True
        assert "document_id" in result
        
        # 返回文档ID
        return result["document_id"]
    
    return _upload_document


class TestDocumentsEndpoints:
    """测试文档API端点"""
    
    @pytest.mark.asyncio
    async def test_list_documents(self, client, my_upload_document):
        """测试获取文档列表"""
        # 上传测试文档
        document_id = await my_upload_document()
        
        # 获取文档列表
        response = client.get("/api/documents")
        
        # 验证响应
        assert response.status_code == 200
        documents = response.json()
        
        # 验证列表内容
        assert isinstance(documents, list)
        assert len(documents) > 0
        
        # 检查上传的文档是否在列表中
        found = False
        for doc in documents:
            if doc["document_id"] == document_id:
                found = True
                break
        
        assert found, "上传的文档应该出现在文档列表中"
    
    @pytest.mark.asyncio
    async def test_get_document_info(self, client, my_upload_document):
        """测试获取文档详情"""
        # 上传测试文档
        document_id = await my_upload_document()
        
        # 获取文档详情
        response = client.get(f"/api/documents/{document_id}")
        
        # 验证响应
        assert response.status_code == 200
        doc_info = response.json()
        
        # 验证文档信息字段
        assert doc_info["document_id"] == document_id
        assert doc_info["original_name"] == "sample.txt"
        assert doc_info["type"] == "txt"
        assert "state" in doc_info
        assert "sub_state" in doc_info
        assert doc_info["state"] == "uploaded"
        assert doc_info["sub_state"] == "completed"
    
    @pytest.mark.asyncio
    async def test_convert_to_markdown(self, client, my_upload_document):
        """测试转换文档为Markdown"""
        # 上传测试文档
        document_id = await my_upload_document()
        
        # 转换为Markdown
        response = client.post(f"/api/documents/{document_id}/convert")
        
        # 验证响应
        assert response.status_code == 200
        result = response.json()
        
        # 验证转换结果
        assert result["success"] is True
        assert result["document_id"] == document_id
        assert "current_state" in result
        assert result["current_state"] in ["markdowned", "markdowning"]
        
        # 等待转换完成
        # 在真实环境中可能需要等待
        time.sleep(1)
        
        # 获取文档详情检查状态
        doc_response = client.get(f"/api/documents/{document_id}")
        doc_info = doc_response.json()
        
        # 状态应该已更新
        assert doc_info["state"] in ["markdowned", "markdowning"]
    
    @pytest.mark.asyncio
    async def test_document_state_transition(self, client, my_upload_document):
        """测试文档状态转换流程"""
        # 上传测试文档
        document_id = await my_upload_document()
        
        # 1. 转换为Markdown
        convert_response = client.post(f"/api/documents/{document_id}/convert")
        assert convert_response.status_code == 200
        time.sleep(1)  # 等待处理完成
        
        # 验证状态
        doc_response = client.get(f"/api/documents/{document_id}")
        doc_info = doc_response.json()
        assert doc_info["state"] == "markdowned"
        
        # 2. 转换为文档切片
        chunk_response = client.post(f"/api/documents/{document_id}/chunks")
        assert chunk_response.status_code == 200
        time.sleep(1)  # 等待处理完成
        
        # 验证状态
        doc_response = client.get(f"/api/documents/{document_id}")
        doc_info = doc_response.json()
        assert doc_info["state"] == "chunked"
        
        # 3. 创建向量索引
        index_response = client.post(f"/api/documents/{document_id}/index")
        assert index_response.status_code == 200
        time.sleep(1)  # 等待处理完成
        
        # 验证状态
        doc_response = client.get(f"/api/documents/{document_id}")
        doc_info = doc_response.json()
        assert doc_info["state"] == "embedded"
    
    @pytest.mark.asyncio
    async def test_get_documents_status(self, client, my_upload_document):
        """测试批量获取文档状态"""
        # 上传测试文档
        document_id = await my_upload_document()
        
        # 请求文档状态
        response = client.post(
            "/api/documents/status",
            json={"document_ids": [document_id]}
        )
        
        # 验证响应
        assert response.status_code == 200
        result = response.json()
        
        # 验证结果
        assert result["success"] is True
        assert result["count"] == 1
        assert result["found_count"] == 1
        assert document_id in result["results"]
        
        # 验证文档状态信息
        doc_status = result["results"][document_id]
        assert doc_status["found"] is True
        assert doc_status["document_id"] == document_id
        assert "process_state" in doc_status
        assert "sub_state" in doc_status
        assert doc_status["process_state"] == "uploaded"
        assert doc_status["sub_state"] == "completed"
    
    @pytest.mark.asyncio
    async def test_get_document_markdown(self, client, my_upload_document):
        """测试获取文档Markdown内容"""
        # 上传并转换文档
        document_id = await my_upload_document()
        client.post(f"/api/documents/{document_id}/convert")
        time.sleep(1)  # 等待处理完成
        
        # 获取Markdown内容
        response = client.get(f"/api/documents/{document_id}/markdown")
        
        # 验证响应
        assert response.status_code == 200
        result = response.json()
        
        # 验证结果
        assert result["success"] is True
        assert result["document_id"] == document_id
        assert "content" in result
        assert result["content"] is not None
        assert isinstance(result["content"], str)
        assert len(result["content"]) > 0
    
    @pytest.mark.asyncio
    async def test_bookmark_remote_document(self, client):
        """测试收藏远程URL文档"""
        # 创建远程书签
        response = client.post(
            "/api/documents/bookmark",
            json={
                "url": "https://example.com/sample.pdf",
                "filename": "示例文档.pdf",
                "title": "示例文档标题",
                "description": "这是一个示例远程文档"
            }
        )
        
        # 验证响应
        assert response.status_code == 200
        result = response.json()
        
        # 验证结果
        assert result["success"] is True
        assert "document_id" in result
        assert result["source_type"] == "remote"
        assert result["source_url"] == "https://example.com/sample.pdf"
    
    @pytest.mark.asyncio
    async def test_storage_status(self, client, my_upload_document):
        """测试获取存储状态"""
        # 上传测试文档
        await my_upload_document()
        
        # 获取存储状态
        response = client.get("/api/documents/storage/status")
        
        # 验证响应
        assert response.status_code == 200
        status = response.json()
        
        # 验证结果字段
        assert "used" in status
        assert "limit" in status
        assert "available" in status
        assert "usage_percentage" in status
        assert "document_count" in status
        assert status["document_count"] > 0
        assert status["used"] > 0
        assert status["limit"] > status["used"]
    
    @pytest.mark.asyncio
    async def test_delete_document(self, client, my_upload_document):
        """测试删除文档"""
        # 上传测试文档
        document_id = await my_upload_document()
        
        # 删除文档
        response = client.delete(f"/api/documents/{document_id}")
        
        # 验证响应
        assert response.status_code == 200
        result = response.json()
        
        # 验证删除结果
        assert result["success"] is True
        assert "message" in result
        
        # 验证文档已被删除 - 获取文档应返回404
        get_response = client.get(f"/api/documents/{document_id}")
        assert get_response.status_code == 404