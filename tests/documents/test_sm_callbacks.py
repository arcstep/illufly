import pytest
import tempfile
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from illufly.documents.sm import DocumentStateMachine
from illufly.documents.meta import DocumentMetaManager


@pytest.fixture
def temp_dir():
    """创建临时目录用于测试"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def meta_manager(temp_dir):
    """创建元数据管理器实例"""
    meta_dir = f"{temp_dir}/meta"
    docs_dir = f"{temp_dir}/docs"
    return DocumentMetaManager(meta_dir, docs_dir)


@pytest.fixture
def user_id():
    return "test_user"


@pytest.fixture
def document_id():
    return "test_doc_123"


@pytest.fixture
def mock_callbacks():
    """创建模拟回调函数字典"""
    callbacks = {
        # 前进回调
        "after_uploaded_to_markdowned": AsyncMock(),
        "after_markdowned_to_chunked": AsyncMock(),
        "after_chunked_to_embedded": AsyncMock(),
        
        # 前置回调
        "before_uploaded_to_markdowned": AsyncMock(),
        
        # 回退回调 - 名称必须与状态回退路径完全匹配
        "before_rollback_embedded_to_chunked": AsyncMock(),
        "before_rollback_chunked_to_markdowned": AsyncMock(),
        "before_rollback_markdowned_to_uploaded": AsyncMock(),
    }
    return callbacks


@pytest.fixture
async def state_machine(meta_manager, user_id, document_id, mock_callbacks):
    """创建带模拟回调的状态机"""
    await meta_manager.create_document(user_id, document_id)
    
    # 创建带回调的状态机
    machine = DocumentStateMachine(
        meta_manager, 
        user_id, 
        document_id, 
        logger=MagicMock(),
        callbacks=mock_callbacks
    )
    await machine.initialize_from_metadata()
    return machine


@pytest.mark.asyncio
async def test_forward_callbacks(state_machine, mock_callbacks):
    """测试状态前进时的回调调用"""
    # 设置初始状态
    await state_machine.set_state("uploaded")
    
    # 转换到markdowned，应该调用前置和后置回调
    await state_machine.set_state("markdowned")
    
    # 验证回调调用
    mock_callbacks["before_uploaded_to_markdowned"].assert_called_once()
    mock_callbacks["after_uploaded_to_markdowned"].assert_called_once()
    
    # 转换到chunked，应该调用对应回调
    await state_machine.set_state("chunked")
    mock_callbacks["after_markdowned_to_chunked"].assert_called_once()
    
    # 转换到embedded，应该调用对应回调
    await state_machine.set_state("embedded")
    mock_callbacks["after_chunked_to_embedded"].assert_called_once()


@pytest.mark.asyncio
async def test_rollback_callbacks(meta_manager, user_id, mock_callbacks):
    """测试状态回退时的回调调用"""
    # 创建一个全新的测试文档
    document_id = "test_rollback_fresh"
    await meta_manager.create_document(user_id, document_id)
    
    # 创建状态机并设置直接前进的回调函数
    machine = DocumentStateMachine(
        meta_manager,
        user_id,
        document_id,
        callbacks=mock_callbacks
    )
    await machine.initialize_from_metadata()
    
    # 直接设置状态并检查每一步
    assert await machine.set_state("uploaded") is True
    assert await machine.get_current_state() == "uploaded"
    
    assert await machine.set_state("markdowned") is True
    assert await machine.get_current_state() == "markdowned"
    
    assert await machine.set_state("chunked") is True
    assert await machine.get_current_state() == "chunked"
    
    assert await machine.set_state("embedded") is True
    assert await machine.get_current_state() == "embedded"
    
    # 重置回调计数
    for callback in mock_callbacks.values():
        callback.reset_mock()
    
    # 执行第一次回退
    assert await machine.rollback() is True
    assert await machine.get_current_state() == "chunked"
    mock_callbacks["before_rollback_embedded_to_chunked"].assert_called_once()
    
    # 检查状态并重置回调计数
    for callback in mock_callbacks.values():
        callback.reset_mock()
    
    # 执行第二次回退
    assert await machine.rollback() is True
    assert await machine.get_current_state() == "markdowned"
    mock_callbacks["before_rollback_chunked_to_markdowned"].assert_called_once()


@pytest.mark.asyncio
async def test_sub_state_processing_failure_and_recovery(state_machine, mock_callbacks):
    """测试子状态处理失败和恢复"""
    # 设置初始状态
    await state_machine.set_state("uploaded")
    
    # 开始处理
    await state_machine.start_processing("markdowned")
    assert (await state_machine.get_current_state_info())["sub_state"] == "processing"
    
    # 处理失败
    await state_machine.fail_processing("markdowned", "处理失败")
    state_info = await state_machine.get_current_state_info()
    assert state_info["state"] == "markdowned"
    assert state_info["sub_state"] == "failed"
    
    # 尝试回退 - 应该只修复子状态，不触发回退回调
    await state_machine.rollback()
    state_info = await state_machine.get_current_state_info()
    assert state_info["state"] == "markdowned"  # 主状态不变
    assert state_info["sub_state"] == "completed"  # 子状态恢复
    
    # 验证没有调用回退回调
    mock_callbacks["before_rollback_markdowned_to_uploaded"].assert_not_called()


@pytest.mark.asyncio
async def test_callback_failure_handling(meta_manager, user_id, document_id):
    """测试回调执行失败的处理"""
    # 创建文档
    await meta_manager.create_document(user_id, document_id)
    
    # 创建带失败回调的状态机
    failing_callbacks = {
        "after_uploaded_to_markdowned": AsyncMock(side_effect=Exception("回调执行失败")),
        "before_rollback_markdowned_to_uploaded": AsyncMock(side_effect=Exception("回退回调失败"))
    }
    
    logger_mock = MagicMock()
    machine = DocumentStateMachine(
        meta_manager, 
        user_id, 
        document_id, 
        logger=logger_mock,
        callbacks=failing_callbacks
    )
    await machine.initialize_from_metadata()
    
    # 设置初始状态
    await machine.set_state("uploaded")
    
    # 尝试转换状态，回调应该失败
    result = await machine.set_state("markdowned")
    
    # 状态转换应该成功，但会记录错误日志
    assert result is True
    assert machine.current_state.id == "markdowned"
    
    # 记录了错误日志
    logger_mock.error.assert_called()
    
    # 尝试回退，回调也会失败
    result = await machine.rollback()
    assert result is False  # 回退失败
    logger_mock.error.assert_called()


@pytest.mark.asyncio
async def test_state_resource_integration(meta_manager, user_id):
    """测试状态与资源管理集成"""
    document_id = "resource_test_updated"
    await meta_manager.create_document(user_id, document_id)
    
    # 模拟资源创建回调
    async def add_markdown_resource(uid, did):
        await meta_manager.add_resource(uid, did, "markdown", {"path": "test.md"})
    
    async def add_chunks_resource(uid, did):
        await meta_manager.add_resource(uid, did, "chunks", {"count": 10})
    
    # 直接使用同步方式验证资源移除
    async def remove_markdown_resource(uid, did):
        result = await meta_manager.remove_resource(uid, did, "markdown")
        # 添加验证确保资源被移除
        updated_meta = await meta_manager.get_metadata(uid, did)
        resources = updated_meta.get("resources", {})
        assert "markdown" not in resources, f"markdown资源未被成功移除，当前资源: {resources}"
    
    callbacks = {
        "after_uploaded_to_markdowned": add_markdown_resource,
        "after_markdowned_to_chunked": add_chunks_resource,
        "before_rollback_markdowned_to_uploaded": remove_markdown_resource
    }
    
    # 创建状态机
    machine = DocumentStateMachine(
        meta_manager, 
        user_id, 
        document_id,
        callbacks=callbacks
    )
    await machine.initialize_from_metadata()
    
    # 设置状态并添加资源
    await machine.set_state("uploaded")
    await machine.set_state("markdowned")
    
    # 验证资源已添加
    meta = await meta_manager.get_metadata(user_id, document_id)
    assert "markdown" in meta.get("resources", {})
    
    # 添加chunked资源
    await machine.set_state("chunked")
    meta = await meta_manager.get_metadata(user_id, document_id)
    assert "chunks" in meta.get("resources", {})
    
    # 回退并验证资源一致性
    await machine.rollback()  # chunked -> markdowned
    meta = await meta_manager.get_metadata(user_id, document_id)
    assert "markdown" in meta.get("resources", {})
    
    # 回退到uploaded，验证markdowned资源已清理
    await machine.rollback()  # markdowned -> uploaded
    meta = await meta_manager.get_metadata(user_id, document_id)
    assert "markdown" not in meta.get("resources", {})
    
    # 测试ensure_state_resource_consistency
    # 修改状态但不更新资源
    await meta_manager.change_state(user_id, document_id, "markdowned", None, "completed")
    
    # 检查一致性应该触发回退
    fixed = await machine.ensure_state_resource_consistency()
    assert fixed is True
    
    # 验证状态已回退
    meta = await meta_manager.get_metadata(user_id, document_id)
    assert meta["state"] == "uploaded"


@pytest.mark.asyncio
async def test_advance_to_next_with_callbacks(state_machine, mock_callbacks):
    """测试advance_to_next与回调集成"""
    # 设置初始状态
    await state_machine.set_state("uploaded")
    
    # 使用advance_to_next前进状态
    result = await state_machine.advance_to_next()
    assert result is True
    assert state_machine.current_state.id == "markdowned"
    
    # 验证回调被调用
    mock_callbacks["after_uploaded_to_markdowned"].assert_called_once() 