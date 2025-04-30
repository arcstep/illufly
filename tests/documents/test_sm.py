import pytest
import tempfile
import asyncio
import time
from pathlib import Path

from illufly.documents.sm import DocumentStateMachine, DocumentState
from illufly.documents.meta import DocumentMetaManager


@pytest.fixture
def temp_dir():
    """创建临时目录用于测试"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def meta_manager(temp_dir):
    """创建真实的元数据管理器实例"""
    meta_dir = f"{temp_dir}/meta"
    docs_dir = f"{temp_dir}/docs"
    return DocumentMetaManager(meta_dir, docs_dir)


@pytest.fixture
def user_id():
    """用户ID"""
    return "test_user"


@pytest.fixture
def document_id():
    """文档ID"""
    return "test_doc_123"


@pytest.fixture
async def state_machine(meta_manager, user_id, document_id):
    """创建并初始化状态机"""
    # 确保文档元数据存在
    await meta_manager.create_document(user_id, document_id)
    
    machine = DocumentStateMachine(meta_manager, user_id, document_id)
    await machine.initialize_from_metadata()
    return machine


@pytest.fixture
async def uploaded_document(meta_manager, user_id, document_id):
    """创建已上传状态的文档"""
    # 创建文档并设置初始元数据
    doc_id = f"{document_id}_uploaded"
    await meta_manager.create_document(
        user_id,
        doc_id,
        None,  # 无主题路径
        {
            "state": "uploaded", 
            "sub_state": "none",
            "has_markdown": False,
            "has_chunks": False,
            "has_embeddings": False
        }
    )
    
    # 创建状态机
    machine = DocumentStateMachine(meta_manager, user_id, doc_id)
    await machine.initialize_from_metadata()
    return machine


@pytest.mark.asyncio
async def test_init(state_machine):
    """测试状态机初始化"""
    assert state_machine.current_state.id == "init"


@pytest.mark.asyncio
async def test_state_sequences():
    """测试状态序列定义"""
    # 验证文档序列
    assert DocumentStateMachine.DOCUMENT_SEQUENCE == [
        DocumentState.INIT, DocumentState.UPLOADED, DocumentState.MARKDOWNED,
        DocumentState.CHUNKED, DocumentState.EMBEDDED
    ]
    
    # 验证书签序列
    assert DocumentStateMachine.BOOKMARK_SEQUENCE == [
        DocumentState.INIT, DocumentState.BOOKMARKED, DocumentState.MARKDOWNED,
        DocumentState.CHUNKED, DocumentState.EMBEDDED
    ]
    
    # 验证对话序列
    assert DocumentStateMachine.CHAT_SEQUENCE == [
        DocumentState.INIT, DocumentState.SAVED_CHAT, DocumentState.QA_EXTRACTED,
        DocumentState.EMBEDDED
    ]


@pytest.mark.asyncio
async def test_set_state(state_machine, meta_manager, user_id, document_id):
    """测试设置状态"""
    # 从init设置为uploaded
    result = await state_machine.set_state("uploaded")
    assert result is True
    assert state_machine.current_state.id == "uploaded"
    
    # 验证元数据更新
    meta = await meta_manager.get_metadata(user_id, document_id)
    assert meta["state"] == "uploaded"
    assert meta["sub_state"] == "none"
    assert len(meta["state_history"]) == 1


@pytest.mark.asyncio
async def test_invalid_transition(state_machine):
    """测试无效的状态转换"""
    # 从init直接到chunked是无效的
    result = await state_machine.set_state("chunked")
    assert result is False
    assert state_machine.current_state.id == "init"  # 状态不变


@pytest.mark.asyncio
async def test_force_state_change(state_machine):
    """测试强制状态变更"""
    # 使用force参数强制转换到无效状态
    result = await state_machine.set_state("chunked", force=True)
    assert result is True
    assert state_machine.current_state.id == "chunked"


@pytest.mark.asyncio
async def test_document_sequence(meta_manager, user_id):
    """测试文档序列状态转换"""
    # 创建新文档
    doc_id = "doc_sequence_test"
    await meta_manager.create_document(user_id, doc_id)
    
    # 初始化并设置状态
    machine = DocumentStateMachine(meta_manager, user_id, doc_id)
    await machine.initialize_from_metadata()
    await machine.set_state("uploaded")
    assert machine.current_state.id == "uploaded"
    
    # 测试获取正确的序列和下一个状态
    sequence = machine.get_sequence()
    assert sequence == DocumentStateMachine.DOCUMENT_SEQUENCE
    assert machine.get_next_state() == "markdowned"
    
    # 前进到下一个状态
    await machine.advance_to_next()
    assert machine.current_state.id == "markdowned"
    
    # 再次前进
    await machine.advance_to_next()
    assert machine.current_state.id == "chunked"


@pytest.mark.asyncio
async def test_chat_sequence(meta_manager, user_id):
    """测试对话序列状态转换"""
    # 创建新文档
    doc_id = "chat_sequence_test"
    await meta_manager.create_document(user_id, doc_id)
    
    # 初始化并设置状态
    machine = DocumentStateMachine(meta_manager, user_id, doc_id)
    await machine.initialize_from_metadata()
    await machine.set_state("saved_chat")
    assert machine.current_state.id == "saved_chat"
    
    # 测试获取正确的序列和下一个状态
    sequence = machine.get_sequence()
    assert sequence == DocumentStateMachine.CHAT_SEQUENCE
    assert machine.get_next_state() == "qa_extracted"
    
    # 前进到下一个状态
    await machine.advance_to_next()
    assert machine.current_state.id == "qa_extracted"


@pytest.mark.asyncio
async def test_rollback(uploaded_document):
    """测试状态回退"""
    # 从uploaded前进到markdowned
    await uploaded_document.advance_to_next()
    assert uploaded_document.current_state.id == "markdowned"
    
    # 回退到上一个状态
    await uploaded_document.rollback_to_previous()
    assert uploaded_document.current_state.id == "uploaded"


@pytest.mark.asyncio
async def test_sub_states(meta_manager, user_id):
    """测试子状态管理"""
    # 创建新文档
    doc_id = "sub_state_test"
    await meta_manager.create_document(user_id, doc_id)
    
    # 初始化状态机
    machine = DocumentStateMachine(meta_manager, user_id, doc_id)
    await machine.initialize_from_metadata()
    
    # 设置为上传状态并开始处理
    await machine.set_state("uploaded")
    await machine.start_processing("markdowned")
    
    # 验证子状态
    state_info = await machine.get_current_state_info()
    assert state_info["state"] == "markdowned"
    assert state_info["sub_state"] == "processing"
    
    # 验证元数据
    meta = await meta_manager.get_metadata(user_id, doc_id)
    assert meta["state"] == "markdowned"
    assert meta["sub_state"] == "processing"
    
    # 完成处理
    await machine.complete_processing("markdowned")
    state_info = await machine.get_current_state_info()
    assert state_info["sub_state"] == "completed"


@pytest.mark.asyncio
async def test_fail_processing(meta_manager, user_id):
    """测试处理失败状态"""
    # 创建新文档
    doc_id = "fail_process_test"
    await meta_manager.create_document(user_id, doc_id)
    
    # 初始化状态机
    machine = DocumentStateMachine(meta_manager, user_id, doc_id)
    await machine.initialize_from_metadata()
    
    # 设置为上传状态并开始处理
    await machine.set_state("uploaded")
    await machine.start_processing("markdowned")
    
    # 处理失败
    error_message = "转换失败：格式错误"
    await machine.fail_processing("markdowned", error_message)
    
    # 验证状态和详情
    meta = await meta_manager.get_metadata(user_id, doc_id)
    assert meta["state"] == "markdowned"
    assert meta["sub_state"] == "failed"
    assert meta["state_details"]["error"] == error_message


@pytest.mark.asyncio
async def test_state_hooks(meta_manager, user_id):
    """测试状态钩子函数"""
    # 创建新文档
    doc_id = "state_hooks_test"
    await meta_manager.create_document(user_id, doc_id)
    
    # 初始化状态机
    machine = DocumentStateMachine(meta_manager, user_id, doc_id)
    await machine.initialize_from_metadata()
    await machine.set_state("uploaded")
    
    # 进入markdowned状态应该设置has_markdown=True
    await machine.set_state("markdowned")
    
    # 验证元数据字段更新
    meta = await meta_manager.get_metadata(user_id, doc_id)
    assert meta["has_markdown"] is True
    
    # 前进到chunked状态
    await machine.advance_to_next()
    meta = await meta_manager.get_metadata(user_id, doc_id)
    assert meta["has_chunks"] is True
    
    # 前进到embedded状态
    await machine.advance_to_next()
    meta = await meta_manager.get_metadata(user_id, doc_id)
    assert meta["has_embeddings"] is True


@pytest.mark.asyncio
async def test_can_transition_to(meta_manager, user_id):
    """测试状态转换可行性检查"""
    # 创建新文档
    doc_id = "transition_test"
    await meta_manager.create_document(user_id, doc_id)
    
    # 初始化状态机
    machine = DocumentStateMachine(meta_manager, user_id, doc_id)
    await machine.initialize_from_metadata()
    await machine.set_state("uploaded")
    
    # 可以转到下一个序列状态
    assert await machine.can_transition_to("markdowned") is True
    
    # 无法直接跳到later状态
    assert await machine.can_transition_to("embedded") is False
    
    # 可以回到init状态
    assert await machine.can_transition_to("init") is True


@pytest.mark.asyncio
async def test_delete_document_state(meta_manager, user_id):
    """测试删除文档状态"""
    # 创建新文档
    doc_id = "delete_test"
    await meta_manager.create_document(user_id, doc_id)
    
    # 初始化状态机
    machine = DocumentStateMachine(meta_manager, user_id, doc_id)
    await machine.initialize_from_metadata()
    
    # 确认文档存在
    meta = await meta_manager.get_metadata(user_id, doc_id)
    assert meta is not None
    
    # 删除文档
    result = await machine.delete_document_state()
    assert result is True
    
    # 验证已删除
    meta = await meta_manager.get_metadata(user_id, doc_id)
    assert meta is None


@pytest.mark.asyncio
async def test_bookmark_flow(meta_manager, user_id):
    """测试书签流程的状态转换"""
    doc_id = "bookmark_flow_test"
    await meta_manager.create_document(user_id, doc_id)
    
    machine = DocumentStateMachine(meta_manager, user_id, doc_id)
    await machine.initialize_from_metadata()
    
    # 测试init -> bookmarked
    await machine.set_state("bookmarked")
    assert machine.current_state.id == "bookmarked"
    
    # 测试bookmarked -> markdowned
    await machine.set_state("markdowned")
    assert machine.current_state.id == "markdowned"


@pytest.mark.asyncio
async def test_embedding_transitions(meta_manager, user_id):
    """测试嵌入相关的状态转换"""
    doc_id = "embedding_test"
    await meta_manager.create_document(user_id, doc_id)
    
    machine = DocumentStateMachine(meta_manager, user_id, doc_id)
    await machine.initialize_from_metadata()
    
    # 准备chunked状态
    await machine.set_state("uploaded", force=True)
    await machine.set_state("markdowned", force=True)
    await machine.set_state("chunked", force=True)
    
    # 测试chunked -> embedded
    await machine.set_state("embedded")
    assert machine.current_state.id == "embedded"
    
    # 测试embedded -> chunked回退
    await machine.set_state("chunked")
    assert machine.current_state.id == "chunked"


@pytest.mark.asyncio
async def test_qa_embedding_flow(meta_manager, user_id):
    """测试QA提取到嵌入的流程"""
    doc_id = "qa_embedding_test"
    await meta_manager.create_document(user_id, doc_id)
    
    machine = DocumentStateMachine(meta_manager, user_id, doc_id)
    await machine.initialize_from_metadata()
    
    # 设置为saved_chat
    await machine.set_state("saved_chat")
    assert machine.current_state.id == "saved_chat"
    
    # qa_extracted -> embedded
    await machine.set_state("qa_extracted")
    assert machine.current_state.id == "qa_extracted"
    
    await machine.set_state("embedded")
    assert machine.current_state.id == "embedded"
    
    # 测试embedded -> qa_extracted回退
    await machine.set_state("qa_extracted")
    assert machine.current_state.id == "qa_extracted"


@pytest.mark.asyncio
async def test_reset_to_init(meta_manager, user_id):
    """测试重置到初始状态"""
    # 测试从uploaded重置
    doc_id = "reset_test_1"
    await meta_manager.create_document(user_id, doc_id)
    machine = DocumentStateMachine(meta_manager, user_id, doc_id)
    await machine.initialize_from_metadata()
    await machine.set_state("uploaded")
    await machine.set_state("init")
    assert machine.current_state.id == "init"
    
    # 测试从bookmarked重置
    doc_id = "reset_test_2"
    await meta_manager.create_document(user_id, doc_id)
    machine = DocumentStateMachine(meta_manager, user_id, doc_id)
    await machine.initialize_from_metadata()
    await machine.set_state("bookmarked")
    await machine.set_state("init")
    assert machine.current_state.id == "init"