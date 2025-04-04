"""文档处理管道测试模块

测试可观测文档处理管道功能
"""

import pytest
import asyncio
from pathlib import Path
from illufly.docling import (
    DocumentProcessStatus,
    DocumentProcessStage,
    ObservablePipeline,
    ObservablePdfPipeline
)

@pytest.fixture
def status_tracker():
    """创建状态追踪器"""
    return DocumentProcessStatus()

@pytest.fixture
def pipeline(status_tracker):
    """创建基础可观测管道"""
    return ObservablePipeline(status_tracker)

@pytest.fixture
def pdf_pipeline(status_tracker):
    """创建PDF可观测管道"""
    return ObservablePdfPipeline(None, status_tracker)

def test_pipeline_initialization(pipeline):
    """测试管道初始化"""
    assert pipeline.status_tracker is not None
    assert pipeline._current_stage == DocumentProcessStage.INITIALIZED
    assert pipeline._current_progress == 0.0
    assert pipeline._current_message == ""

def test_pipeline_progress_logging(pipeline):
    """测试进度记录"""
    # 记录进度
    pipeline._log_progress(
        DocumentProcessStage.LOADING,
        0.5,
        "正在加载文档"
    )
    
    # 验证状态更新
    assert pipeline._current_stage == DocumentProcessStage.LOADING
    assert pipeline._current_progress == 0.5
    assert pipeline._current_message == "正在加载文档"
    assert pipeline.status_tracker.stage == DocumentProcessStage.LOADING
    assert pipeline.status_tracker.progress == 0.5

@pytest.mark.asyncio
async def test_pipeline_progress_monitoring(pipeline):
    """测试进度监控"""
    # 启动监控
    pipeline._processing = True
    monitor_task = asyncio.create_task(pipeline._progress_monitor())
    
    # 更新进度
    pipeline._log_progress(
        DocumentProcessStage.PROCESSING,
        0.3,
        "处理中"
    )
    
    # 等待一段时间
    await asyncio.sleep(2)
    
    # 停止监控
    pipeline._processing = False
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass
    
    # 验证状态更新
    assert pipeline.status_tracker.stage == DocumentProcessStage.PROCESSING
    assert pipeline.status_tracker.progress == 0.3

def test_pdf_pipeline_initialization(pdf_pipeline):
    """测试PDF管道初始化"""
    assert pdf_pipeline.status_tracker is not None
    assert isinstance(pdf_pipeline, ObservablePdfPipeline)
    assert pdf_pipeline._current_stage == DocumentProcessStage.INITIALIZED

def test_pdf_pipeline_intermediate_results(pdf_pipeline):
    """测试PDF管道中间结果"""
    # 设置中间结果
    pdf_pipeline.intermediate_results = {
        "pages_processed": 5,
        "total_pages": 10,
        "current_text": "测试内容",
        "page_texts": ["第1页", "第2页"]
    }
    
    # 验证中间结果
    assert pdf_pipeline.intermediate_results["pages_processed"] == 5
    assert pdf_pipeline.intermediate_results["total_pages"] == 10
    assert pdf_pipeline.intermediate_results["current_text"] == "测试内容"
    assert len(pdf_pipeline.intermediate_results["page_texts"]) == 2

@pytest.mark.asyncio
async def test_pdf_pipeline_progress_monitoring(pdf_pipeline):
    """测试PDF管道进度监控"""
    # 设置中间结果
    pdf_pipeline.intermediate_results = {
        "pages_processed": 3,
        "total_pages": 10,
        "current_text": "测试内容",
        "page_texts": ["第1页", "第2页", "第3页"]
    }
    
    # 启动监控
    pdf_pipeline._processing = True
    monitor_task = asyncio.create_task(pdf_pipeline._progress_monitor())
    
    # 等待一段时间
    await asyncio.sleep(2)
    
    # 停止监控
    pdf_pipeline._processing = False
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass
    
    # 验证状态更新
    assert "已解析页面" in pdf_pipeline.status_tracker.message
    assert "3/10" in pdf_pipeline.status_tracker.message 