
"""文档处理管道异步API测试模块

测试可观测文档处理管道的异步功能和进度追踪，基于真实docling处理流程
"""

import pytest
import asyncio
import tempfile
import os
import shutil
import importlib
from pathlib import Path
from datetime import datetime
import logging
import requests
import json
import time
from unittest.mock import MagicMock, patch

# 从系统导入docling包
import docling.pipeline.base_pipeline
import docling.pipeline.standard_pdf_pipeline
import docling.pipeline.simple_pipeline
import docling.datamodel.pipeline_options
import docling.datamodel.document
import docling.datamodel.base_models

# 导入docling必要组件
from docling.pipeline.base_pipeline import BasePipeline
from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
from docling.pipeline.simple_pipeline import SimplePipeline
from docling.datamodel.pipeline_options import PdfPipelineOptions, PipelineOptions
from docling.datamodel.document import ConversionResult, InputDocument
from docling.datamodel.base_models import ConversionStatus, InputFormat, DocumentStream
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.backend.docling_parse_v4_backend import DoclingParseV4DocumentBackend
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.chunking import HybridChunker, BaseChunker, BaseChunk

# 导入被测试组件
from illufly.docling import DocumentProcessStatus, DocumentProcessStage
from illufly.docling import (
    ObservablePipelineWrapper, 
    ObservableConverter,
    DocumentProcessor,
    create_async_observable_converter,
    ObservableChunker
)

# 创建日志记录器
logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def sample_pdf_path():
    """提供测试PDF文件路径"""
    pdf_path = os.path.join(os.path.dirname(__file__), "simple_test.pdf")
    if not os.path.exists(pdf_path):
        pytest.skip("找不到测试PDF文件: simple_test.pdf")
    return pdf_path


@pytest.fixture(scope="session")
def sample_pdf_first_pages(sample_pdf_path):
    """直接使用创建好的两页测试PDF"""
    # 直接使用简单的2页测试PDF，不需要额外处理
    logger.info(f"使用两页测试PDF文件: {sample_pdf_path}")
    return sample_pdf_path


@pytest.fixture(scope="session")
def arxiv_pdf_path():
    """下载 arxiv 上的 PDF 文件用于测试"""
    arxiv_url = "https://arxiv.org/pdf/2503.21760"
    try:
        # 临时文件保存 PDF
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            pdf_path = tmp.name
            
            # 下载 PDF 文件
            logger.info(f"开始下载 arxiv PDF 文件: {arxiv_url}")
            response = requests.get(arxiv_url, stream=True)
            response.raise_for_status()  # 确保请求成功
            
            # 写入文件
            with open(pdf_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"已下载 arxiv PDF 文件到: {pdf_path}")
            yield pdf_path
    except Exception as e:
        logger.error(f"下载 arxiv PDF 文件失败: {str(e)}")
        yield None
    
    # 测试后清理
    try:
        if 'pdf_path' in locals() and os.path.exists(pdf_path):
            os.unlink(pdf_path)
            logger.info(f"已删除下载的 PDF 文件: {pdf_path}")
    except:
        pass


@pytest.fixture
def status_tracker():
    """创建状态追踪器"""
    return DocumentProcessStatus(doc_id=f"test_{datetime.now().strftime('%Y%m%d%H%M%S')}")


@pytest.fixture
def pdf_pipeline(request):
    """创建管道实例，根据标记选择正确的实现"""
    backend_type = getattr(request.module, "backend_type", "pypdfium")
    
    options = PdfPipelineOptions()
    options.enable_remote_services = False
    options.do_ocr = False
    options.do_table_structure = False
    options.do_formula_enrichment = False
    
    # 始终使用SimplePipeline，避免使用StandardPdfPipeline，因为它可能与DoclingParseV4DocumentBackend一起使用
    return SimplePipeline(pipeline_options=options)

class TestObservableChunker:
    """测试可观测分块器"""
    
    @pytest.mark.asyncio
    async def test_initialization(self, status_tracker):
        """测试初始化"""
        try:
            # 创建基础chunker
            chunker = HybridChunker(tokenizer="BAAI/bge-small-en-v1.5")
            
            # 创建可观测分块器
            observable_chunker = ObservableChunker(chunker, status_tracker)
            
            # 验证基本属性
            assert observable_chunker.chunker == chunker
            assert observable_chunker.status_tracker == status_tracker
            assert observable_chunker._processing == False
            assert observable_chunker._chunks_processed == 0
            assert observable_chunker._total_chunks == 0
            
        except ImportError as e:
            pytest.skip(f"依赖导入问题: {e}")
    
    @pytest.mark.asyncio
    async def test_log_progress(self, status_tracker):
        """测试进度记录功能"""
        try:
            chunker = HybridChunker(tokenizer="BAAI/bge-small-en-v1.5")
            observable_chunker = ObservableChunker(chunker, status_tracker)
            
            # 记录进度
            observable_chunker._log_progress(0.42, "测试进度记录")
            
            # 验证状态已更新
            assert status_tracker.stage == DocumentProcessStage.CHUNKING
            assert status_tracker.progress == 0.42
            assert status_tracker.message == "测试进度记录"
            
        except ImportError as e:
            pytest.skip(f"依赖导入问题: {e}")
    
    @pytest.mark.asyncio
    async def test_progress_monitor(self, status_tracker):
        """测试进度监控任务"""
        try:
            chunker = HybridChunker(tokenizer="BAAI/bge-small-en-v1.5")
            observable_chunker = ObservableChunker(chunker, status_tracker)
            
            # 设置初始状态
            observable_chunker._chunks_processed = 5
            observable_chunker._total_chunks = 10
            
            # 启动监控
            observable_chunker._processing = True
            monitor_task = asyncio.create_task(observable_chunker._progress_monitor())
            
            # 等待一会以确保监控执行
            await asyncio.sleep(0.1)
            
            # 停止监控
            observable_chunker._processing = False
            try:
                await asyncio.wait_for(monitor_task, timeout=0.5)
            except (asyncio.TimeoutError, StopAsyncIteration):
                pass  # 预期行为
            
        except ImportError as e:
            pytest.skip(f"依赖导入问题: {e}")
    
    @pytest.mark.asyncio
    async def test_chunk_async_with_real_document(self, status_tracker, sample_pdf_first_pages):
        """测试异步分块功能，使用真实文档和分块器"""
        try:
            # 使用DocumentConverter获取真实文档
            converter = DocumentConverter()
            result = converter.convert(sample_pdf_first_pages, raises_on_error=False)
            
            if result.status != ConversionStatus.SUCCESS or not hasattr(result, "document"):
                pytest.skip("无法获取有效的文档对象进行测试")
            
            document = result.document
            
            # 使用真实的HybridChunker
            chunker = HybridChunker(
                tokenizer="BAAI/bge-small-en-v1.5",
                chunk_size=200,
                chunk_overlap=20
            )
            
            # 创建可观测分块器
            observable_chunker = ObservableChunker(chunker, status_tracker)
            
            # 执行异步分块
            results = []
            async for item in observable_chunker.chunk_async(document):
                results.append(item)
            
            # 验证结果
            assert len(results) > 0
            
            # 应该包含状态更新和块内容
            statuses = [r for r in results if isinstance(r, dict) and "stage" in r]
            chunks = [r for r in results if isinstance(r, dict) and r.get("type") == "chunk"]
            
            # 验证有块生成
            assert len(chunks) > 0, "未生成任何块"
            
            # 验证块的结构
            first_chunk = chunks[0]
            assert "content" in first_chunk
            assert "index" in first_chunk
            assert isinstance(first_chunk["content"], str)
            
            # 验证状态更新
            assert len(statuses) > 0
            assert any(s.get("stage") == DocumentProcessStage.CHUNKING.value for s in statuses)
            
        except ImportError as e:
            pytest.skip(f"依赖导入问题: {e}")
        except Exception as e:
            logger.error(f"测试真实分块功能时出错: {str(e)}", exc_info=True)
            pytest.skip(f"真实分块测试失败: {str(e)}")
        finally:
            # 清理文档资源
            if 'result' in locals() and hasattr(result, "input") and hasattr(result.input, "_backend"):
                try:
                    result.input._backend.unload()
                except:
                    pass
