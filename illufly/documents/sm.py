from statemachine import StateMachine, State
import time
import logging
from typing import Optional, List, Dict, Any

class DocumentState:
    """文档状态枚举"""
    # 初始状态
    INIT = "init"
    
    # 来源状态
    UPLOADED = "uploaded"
    BOOKMARKED = "bookmarked"
    SAVED_CHAT = "saved_chat"
    
    # 转换后状态
    MARKDOWNED = "markdowned"
    CHUNKED = "chunked"
    QA_EXTRACTED = "qa_extracted"
    EMBEDDED = "embedded"
    
    # 移除这里的序列定义，改为从状态机中提取
    
    @staticmethod
    def is_source_state(state):
        return state in [DocumentState.UPLOADED, DocumentState.BOOKMARKED, DocumentState.SAVED_CHAT]

class DocumentStateMachine(StateMachine):
    """简化的文档状态机 - 支持回调注入"""
    
    # 初始状态 - 文档创建初始点
    init = State('初始化', initial=True)
    
    # 源状态 - 文档来源
    uploaded = State('本地上传')
    bookmarked = State('网络收藏')
    saved_chat = State('对话收藏')
    
    # 转换后状态 - 核心格式
    markdowned = State('Markdown格式')
    chunked = State('切片格式')
    qa_extracted = State('QA对格式')
    embedded = State('向量嵌入格式')
    
    # 从初始状态到各来源的转换
    set_uploaded = init.to(uploaded)      # 设置为上传文档
    set_bookmarked = init.to(bookmarked)  # 设置为网络收藏
    set_saved_chat = init.to(saved_chat)  # 设置为对话记录
    
    # ====== 正向转换 ======
    # 文档序列
    to_markdown_from_file = uploaded.to(markdowned)
    to_markdown_from_web = bookmarked.to(markdowned)
    to_chunks = markdowned.to(chunked)
    chunks_to_embeddings = chunked.to(embedded)
    
    # 对话序列
    to_qa_pairs = saved_chat.to(qa_extracted)
    qa_to_embeddings = qa_extracted.to(embedded)
    
    # ====== 回退转换 ======
    # 文档序列回退
    revert_markdown = markdowned.to(uploaded, bookmarked)
    revert_chunks = chunked.to(markdowned)
    revert_doc_embeddings = embedded.to(chunked)
    
    # 对话序列回退
    revert_qa = qa_extracted.to(saved_chat)
    revert_qa_embeddings = embedded.to(qa_extracted)
    
    # 可能的彻底重置
    reset_to_init = uploaded.to(init) | bookmarked.to(init) | saved_chat.to(init)
    
    # 定义状态序列 - 这是从状态转换中提取的，成为单一事实来源
    DOCUMENT_SEQUENCE = [DocumentState.INIT, DocumentState.UPLOADED, DocumentState.MARKDOWNED, 
                        DocumentState.CHUNKED, DocumentState.EMBEDDED]
    BOOKMARK_SEQUENCE = [DocumentState.INIT, DocumentState.BOOKMARKED, DocumentState.MARKDOWNED, 
                        DocumentState.CHUNKED, DocumentState.EMBEDDED]
    CHAT_SEQUENCE = [DocumentState.INIT, DocumentState.SAVED_CHAT, DocumentState.QA_EXTRACTED, 
                    DocumentState.EMBEDDED]
    
    # 转换序列映射表 - 用于快速查找状态所属的序列
    SEQUENCE_MAP = {
        DocumentState.INIT: [DOCUMENT_SEQUENCE, BOOKMARK_SEQUENCE, CHAT_SEQUENCE],
        DocumentState.UPLOADED: [DOCUMENT_SEQUENCE],
        DocumentState.BOOKMARKED: [BOOKMARK_SEQUENCE],
        DocumentState.SAVED_CHAT: [CHAT_SEQUENCE],
        DocumentState.MARKDOWNED: [DOCUMENT_SEQUENCE, BOOKMARK_SEQUENCE],
        DocumentState.CHUNKED: [DOCUMENT_SEQUENCE, BOOKMARK_SEQUENCE],
        DocumentState.QA_EXTRACTED: [CHAT_SEQUENCE],
        DocumentState.EMBEDDED: [DOCUMENT_SEQUENCE, BOOKMARK_SEQUENCE, CHAT_SEQUENCE]
    }
    
    # 子状态定义
    class SubState:
        """文档处理子状态"""
        PROCESSING = "processing"  # 处理中
        COMPLETED = "completed"    # 完成
        FAILED = "failed"          # 失败
        NONE = "none"              # 无子状态
    
    # 添加到 DocumentStateMachine 类中
    RESOURCE_STATE_MAP = {
        "markdown": DocumentState.MARKDOWNED,
        "chunks": DocumentState.CHUNKED,
        "qa_pairs": DocumentState.QA_EXTRACTED, 
        "embeddings": DocumentState.EMBEDDED
    }
    
    def __init__(self, meta_manager, user_id, document_id, logger=None, callbacks=None):
        self.meta_manager = meta_manager
        self.user_id = user_id
        self.document_id = document_id
        self.logger = logger or logging.getLogger(__name__)
        self.previous_state = None
        # 注册回调函数字典
        self.callbacks = callbacks or {}
        super().__init__()
    
    @classmethod
    def get_all_sequences(cls) -> List[List[str]]:
        """获取所有已定义的状态序列"""
        return [cls.DOCUMENT_SEQUENCE, cls.BOOKMARK_SEQUENCE, cls.CHAT_SEQUENCE]
    
    @classmethod
    def find_sequence_for_state(cls, state: str) -> List[List[str]]:
        """查找包含指定状态的所有序列"""
        return cls.SEQUENCE_MAP.get(state, [])
    
    async def get_current_state(self) -> str:
        """从元数据获取当前状态"""
        meta = await self.meta_manager.get_metadata(self.user_id, self.document_id)
        if not meta or "state" not in meta:
            return "init"  # 默认状态改为init
        
        # 映射元数据状态到状态机状态
        state_map = {
            "init": "init",
            "uploaded": "uploaded",
            "bookmarked": "bookmarked", 
            "saved_chat": "saved_chat",
            "markdowned": "markdowned",
            "chunked": "chunked",
            "qa_extracted": "qa_extracted",
            "embedded": "embedded"
        }
        
        return state_map.get(meta["state"], "init")
    
    async def set_state(self, new_state: str, details: dict = None, sub_state: str = SubState.NONE, force: bool = False) -> bool:
        """设置状态并更新元数据，支持子状态和回调执行"""
        # 保存之前的状态
        old_state = await self.get_current_state()
        self.previous_state = old_state
        
        # 如果不是强制模式，验证状态转换是否有效
        if not force and old_state != new_state:
            can_transition = await self.can_transition_to(new_state)
            if not can_transition:
                self.logger.warning(f"无效的状态转换: {old_state} -> {new_state}")
                return False
        
        # 根据状态名获取状态对象
        target_state = None
        for state in self.states:
            if state.id == new_state:
                target_state = state
                break
        
        # 执行状态转换
        if target_state:
            # 1. 更新内部状态
            self.current_state = target_state
            
            # 2. 执行前置回调（如果存在）
            before_callback_name = f"before_{old_state}_to_{new_state}"
            if before_callback_name in self.callbacks:
                try:
                    await self.callbacks[before_callback_name](self.user_id, self.document_id)
                except Exception as e:
                    self.logger.error(f"执行前置回调失败: {before_callback_name}, 错误: {e}")
                    return False
            
            # 3. 更新元数据
            success = await self.meta_manager.change_state(
                self.user_id, self.document_id, 
                new_state, details, sub_state
            )
            
            if not success:
                self.logger.error(f"文档 {self.document_id} 元数据状态更新失败")
                return False
            
            # 4. 调用进入状态的钩子函数
            hook_method = f"on_enter_{new_state}"
            if hasattr(self, hook_method):
                await getattr(self, hook_method)(old_state)
            
            # 5. 执行后置回调（如果存在）
            after_callback_name = f"after_{old_state}_to_{new_state}"
            if after_callback_name in self.callbacks:
                try:
                    await self.callbacks[after_callback_name](self.user_id, self.document_id)
                except Exception as e:
                    self.logger.error(f"执行后置回调失败: {after_callback_name}, 错误: {e}")
                    # 不影响状态转换结果，但记录日志
            
            self.logger.info(f"文档 {self.document_id} 状态从 {old_state} 变更为 {new_state}[{sub_state}]")
            return True
        
        return False
    
    async def initialize_from_metadata(self):
        """根据元数据初始化状态"""
        current_state = await self.get_current_state()
        
        # 设置初始状态
        for state in self.states:
            if state.id == current_state:
                self.current_state = state
                break
    
    async def on_enter_markdowned(self, from_state=None):
        """进入Markdown完成状态 - 仅处理清理逻辑
        
        当状态转为markdowned时，如果是从chunked状态回退，
        需要清理chunks资源以保持状态与资源一致性。
        """
        # 仅保留清理逻辑，删除资源添加代码
        if from_state == "chunked":
            await self.meta_manager.remove_resource(
                self.user_id, self.document_id, "chunks"
            )
    
    async def on_enter_chunked(self, from_state=None):
        """进入切片完成状态 - 仅处理清理逻辑
        
        当状态转为chunked时，如果是从embedded状态回退，
        需要清理embeddings资源以保持状态与资源一致性。
        """
        # 仅保留清理逻辑，删除资源添加代码
        if from_state == "embedded":
            await self.meta_manager.remove_resource(
                self.user_id, self.document_id, "embeddings"
            )
    
    async def on_enter_qa_extracted(self, from_state=None):
        """进入QA提取完成状态 - 仅处理清理逻辑
        
        当状态转为qa_extracted时，如果是从embedded状态回退，
        需要清理embeddings资源以保持状态与资源一致性。
        """
        # 仅保留清理逻辑，删除资源添加代码
        if from_state == "embedded":
            await self.meta_manager.remove_resource(
                self.user_id, self.document_id, "embeddings"
            )
    
    async def on_enter_embedded(self, from_state=None):
        """进入嵌入完成状态 - 无需特殊处理"""
        pass
    
    async def on_enter_init(self, from_state=None):
        """进入初始状态 - 可选清理所有资源"""
        # 可选实现：清理所有资源
        pass
    
    async def on_enter_uploaded(self, from_state=None):
        """进入上传状态 - 无需特殊处理"""
        pass

    async def on_enter_bookmarked(self, from_state=None):
        """进入书签状态 - 无需特殊处理"""
        pass
    
    # 辅助方法
    def get_sequence(self) -> list:
        """获取当前文档的状态序列"""
        current_id = self.current_state.id
        
        # 如果当前状态是embedded，可能需要根据previous_state判断来源
        if current_id == DocumentState.EMBEDDED:
            if self.previous_state == DocumentState.CHUNKED:
                return self.DOCUMENT_SEQUENCE if self.previous_state.startswith("uploaded") else self.BOOKMARK_SEQUENCE
            elif self.previous_state == DocumentState.QA_EXTRACTED:
                return self.CHAT_SEQUENCE
        
        # 使用SEQUENCE_MAP查找当前状态所属的序列
        sequences = self.find_sequence_for_state(current_id)
        if sequences:
            # 如果有多个序列包含此状态，优先使用与先前状态一致的序列
            if len(sequences) > 1 and self.previous_state:
                for seq in sequences:
                    if self.previous_state in seq:
                        return seq
            # 否则返回第一个包含此状态的序列
            return sequences[0]
        
        # 默认返回DOCUMENT_SEQUENCE
        return self.DOCUMENT_SEQUENCE
    
    def get_next_state(self) -> Optional[str]:
        """获取序列中的下一个状态"""
        sequence = self.get_sequence()
        current_id = self.current_state.id
        
        try:
            current_idx = sequence.index(current_id)
            if current_idx < len(sequence) - 1:
                return sequence[current_idx + 1]
        except ValueError:
            # 可能是因为current_id不在序列中
            pass
        
        return None

    def get_previous_state(self) -> Optional[str]:
        """获取序列中的上一个状态"""
        sequence = self.get_sequence()
        current_id = self.current_state.id
        
        try:
            current_idx = sequence.index(current_id)
            if current_idx > 0:
                return sequence[current_idx - 1]
        except ValueError:
            # 可能是因为current_id不在序列中
            pass
        
        return None

    async def can_transition_to(self, target_state: str) -> bool:
        """检查是否可以转换到目标状态"""
        current_id = self.current_state.id
        
        # 明确允许的转换
        allowed_transitions = {
            "init": ["uploaded", "bookmarked", "saved_chat"],
            "uploaded": ["markdowned"],
            "bookmarked": ["markdowned"],
            "markdowned": ["chunked", "uploaded", "bookmarked"],
            "chunked": ["embedded", "markdowned"],
            "embedded": ["chunked", "qa_extracted"],
            "saved_chat": ["qa_extracted"]
        }
        
        # 检查明确允许的转换
        if current_id in allowed_transitions and target_state in allowed_transitions[current_id]:
            return True
        
        # 检查序列中的下一个/上一个状态
        if target_state == self.get_next_state():
            return True
        if target_state == self.get_previous_state():
            return True
        
        # 特殊转换规则检查（此处仍可保留一些业务规则）
        if current_id == "markdowned" and target_state in ["uploaded", "bookmarked"]:
            return True
        if current_id == "embedded" and target_state in ["chunked", "qa_extracted"]:
            return True
            
        return False
    
    # 高级操作
    async def advance_to_next(self, details=None) -> bool:
        """前进到序列中的下一个状态"""
        next_state = self.get_next_state()
        if next_state:
            return await self.set_state(next_state, details)
        return False
    

    async def get_current_state_info(self) -> Dict[str, str]:
        """获取当前完整状态信息，包括主状态和子状态"""
        meta = await self.meta_manager.get_metadata(self.user_id, self.document_id)
        if not meta:
            return {
                "state": "init",
                "sub_state": DocumentStateMachine.SubState.NONE
            }
        
        # 映射元数据状态到状态机状态
        state_map = {
            "init": "init",
            "uploaded": "uploaded",
            "bookmarked": "bookmarked", 
            "saved_chat": "saved_chat",
            "markdowned": "markdowned",
            "chunked": "chunked",
            "qa_extracted": "qa_extracted",
            "embedded": "embedded"
        }
        
        return {
            "state": state_map.get(meta.get("state", "init"), "init"),
            "sub_state": meta.get("sub_state", DocumentStateMachine.SubState.NONE)
        }

    async def delete_document_state(self) -> bool:
        """删除文档状态"""
        return await self.meta_manager.delete_document(self.user_id, self.document_id)

    async def start_processing(self, target_state: str) -> bool:
        """开始处理过程，设置子状态为processing"""
        return await self.set_state(
            target_state, 
            sub_state=self.SubState.PROCESSING
        )
    
    async def complete_processing(self, state: str) -> bool:
        """完成处理过程，设置子状态为completed"""
        return await self.set_state(
            state, 
            sub_state=self.SubState.COMPLETED
        )
    
    async def fail_processing(self, state: str, error: str) -> bool:
        """处理失败，设置子状态为failed"""
        return await self.set_state(
            state, 
            sub_state=self.SubState.FAILED,
            details={"error": error}
        )

    async def activate_initial_state(self):
        """激活初始状态并与元数据同步"""
        # 首先从元数据读取当前状态
        meta_state = await self.get_current_state()
        
        # 如果元数据已有状态，则使用该状态
        if meta_state != "init":
            for state in self.states:
                if state.id == meta_state:
                    self.current_state = state
                    return
        
        # 否则使用默认初始状态
        await super().activate_initial_state()

    async def rollback(self) -> bool:
        """改进的回退逻辑，支持回调函数，并正确管理状态历史"""
        # 1. 获取当前状态和子状态
        state_info = await self.get_current_state_info()
        current_state = state_info["state"]
        current_sub_state = state_info["sub_state"]

        # 情况1：子状态为 processing 或 failed，只回退子状态到 completed
        if current_sub_state in [self.SubState.PROCESSING, self.SubState.FAILED]:
            return await self.set_state(
                current_state,
                sub_state=self.SubState.COMPLETED
            )

        # 情况2：主状态回退，按历史记录前进
        meta = await self.meta_manager.get_metadata(self.user_id, self.document_id)
        if not meta:
            self.logger.error(f"回退失败：无法获取文档 {self.document_id} 元数据")
            return False

        history = meta.get("state_history", [])
        if len(history) <= 1:
            self.logger.warning(f"无法回退：文档 {self.document_id} 状态历史不足")
            return False

        # 前一个状态记录
        prev_record = history[-2]
        prev_state = prev_record["state"]
        prev_sub_state = prev_record.get("sub_state", self.SubState.COMPLETED)

        # 回退前回调
        cb_name = f"before_rollback_{current_state}_to_{prev_state}"
        if cb_name in self.callbacks:
            try:
                self.logger.info(f"调用回退回调: {cb_name}")
                await self.callbacks[cb_name](self.user_id, self.document_id)
            except Exception as e:
                self.logger.error(f"回退回调失败 {cb_name}: {e}")
                return False

        # 裁剪掉最新一条历史，并更新状态
        new_history = history[:-1]
        await self.meta_manager.update_metadata(
            self.user_id,
            self.document_id,
            {
                "state": prev_state,
                "sub_state": prev_sub_state,
                "state_history": new_history
            }
        )

        # 更新状态机内部 current_state
        for st in self.states:
            if st.id == prev_state:
                self.current_state = st
                break

        # 调用对应 on_enter 钩子清理资源
        hook = f"on_enter_{prev_state}"
        if hasattr(self, hook):
            await getattr(self, hook)(current_state)

        self.logger.info(f"文档 {self.document_id} 回退到 {prev_state}[{prev_sub_state}]")
        return True

    async def ensure_state_resource_consistency(self) -> bool:
        """确保文档状态和资源一致性
        
        根据文档当前状态检查必要资源是否存在，如不存在则修复。
        此方法应该在加载文档时检查使用。
        
        Returns:
            bool: 是否需要进行修复
        """
        current_state = await self.get_current_state()
        meta = await self.meta_manager.get_metadata(self.user_id, self.document_id)
        
        if not meta:
            return False
        
        resources = meta.get("resources", {})
        fixed = False
        
        # 检查并修复资源状态一致性
        if current_state == "markdowned" and "markdown" not in resources:
            # 状态为markdowned但缺少markdown资源，进行降级
            await self.rollback()
            fixed = True
        
        elif current_state == "chunked" and "chunks" not in resources:
            # 状态为chunked但缺少chunks资源，进行降级
            await self.rollback()
            fixed = True
        
        elif current_state == "embedded" and "embeddings" not in resources:
            # 状态为embedded但缺少embeddings资源，进行降级 
            await self.rollback()
            fixed = True
        
        return fixed
