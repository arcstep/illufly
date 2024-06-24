from __future__ import annotations

import inspect
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
    Type,
    Union,
)

from langchain.memory import ConversationBufferMemory
from langchain.memory.chat_memory import BaseChatMemory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.load.load import load
from langchain_core.pydantic_v1 import BaseModel
from langchain_core.runnables.base import Runnable, RunnableBindingBase, RunnableLambda
from langchain_core.runnables.config import run_in_executor
from langchain_core.runnables.passthrough import RunnablePassthrough
from langchain_core.runnables.utils import (
    ConfigurableFieldSpec,
    create_model,
    get_unique_config_specs,
)

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage
    from langchain_core.runnables.config import RunnableConfig
    from langchain_core.tracers.schemas import Run

MessagesOrDictWithMessages = Union[Sequence["BaseMessage"], Dict[str, Any]]
GetSessionHistoryCallable = Callable[..., BaseChatMessageHistory]

from .memory_manager import MemoryManager
from ..config import get_default_session

class WithMemoryBinding(RunnableBindingBase):
    """Runnable that manages memory for another Runnable."""

    # 记忆管理
    memory_manager: MemoryManager
    input_messages_key: Optional[str] = None
    output_messages_key: Optional[str] = None
    history_messages_key: Optional[str] = None
    history_factory_config: Sequence[ConfigurableFieldSpec]

    @classmethod
    def get_lc_namespace(cls) -> List[str]:
        """Get the namespace of the langchain object."""
        return ["langchain", "schema", "runnable"]

    def __init__(
        self,
        runnable: Runnable[
            MessagesOrDictWithMessages,
            Union[str, BaseMessage, MessagesOrDictWithMessages],
        ],
        memory_manager: MemoryManager,
        *,
        input_messages_key: Optional[str] = "input",
        output_messages_key: Optional[str] = None,
        history_messages_key: Optional[str] = "history",
        **kwargs: Any,
    ) -> None:
        # 提取记忆 _current_history / _acurrent_history
        history_chain = RunnablePassthrough.assign(
            **{history_messages_key: RunnableLambda(self._current_history, self._acurrent_history)}
        ).with_config(run_name="insert_history")

        # 写入记忆 _update_history
        bound = (
            history_chain | runnable
        ).with_listeners(on_end=self._update_history)

        # 构造 config.configurable 中的参数，可以被 Runnable 自举
        _config_specs = [
            ConfigurableFieldSpec(
                id="session_id",
                annotation=str,
                name="Session ID",
                description="Unique identifier for a session.",
                default="",
                is_shared=True,
            ),
        ]

        super().__init__(
            memory_manager=memory_manager,
            input_messages_key=input_messages_key,
            output_messages_key=output_messages_key,
            bound=bound,
            history_messages_key=history_messages_key,
            history_factory_config=_config_specs,
            **kwargs,
        )

    @property
    def config_specs(self) -> List[ConfigurableFieldSpec]:
        """构造记忆录入的参数"""
        return get_unique_config_specs(
            super().config_specs + list(self.history_factory_config)
        )

    def get_input_schema(
        self, config: Optional[RunnableConfig] = None
    ) -> Type[BaseModel]:
        super_schema = super().get_input_schema(config)
        if super_schema.__custom_root_type__ or not super_schema.schema().get(
            "properties"
        ):
            from langchain_core.messages import BaseMessage

            fields = {self.input_messages_key: (
                Union[str, BaseMessage, Sequence[BaseMessage]],
                ...,
            )}
            return create_model(
                "RunnableWithChatHistoryInput",
                **fields,
            )
        else:
            return super_schema

    def _get_input_messages(
        self, input_val: Union[str, BaseMessage, Sequence[BaseMessage]]
    ) -> List[BaseMessage]:
        """从Runnable的输入中，提取要保存的部份"""
        from langchain_core.messages import BaseMessage

        if isinstance(input_val, str):
            from langchain_core.messages import HumanMessage

            return [HumanMessage(content=input_val)]
        elif isinstance(input_val, BaseMessage):
            return [input_val]
        elif isinstance(input_val, (list, tuple)):
            return list(input_val)
        else:
            raise ValueError(
                f"Expected str, BaseMessage, List[BaseMessage], or Tuple[BaseMessage]. "
                f"Got {input_val}."
            )

    def _get_output_messages(
        self, output_val: Union[str, BaseMessage, Sequence[BaseMessage], dict]
    ) -> List[BaseMessage]:
        """从Runnable的输出中，提取要保存的部份"""
        from langchain_core.messages import BaseMessage

        # 对于AgentExcutor
        if isinstance(output_val, dict):
            output_val = output_val[self.output_messages_key or "output"]

        # 对于字符串
        if isinstance(output_val, str):
            from langchain_core.messages import AIMessage

            return [AIMessage(content=output_val)]
        
        # 对于BaseMessage
        elif isinstance(output_val, BaseMessage):
            return [output_val]

        # 对于字符串列表、包含字符串的元组
        elif isinstance(output_val, (list, tuple)):
            return list(output_val)

        else:
            raise ValueError()

    def _current_history(self, input: Any, config: RunnableConfig) -> List[BaseMessage]:
        memory = config["configurable"]["memory"]
        return memory.buffer_as_messages

    async def _acurrent_history(
        self, input: Dict[str, Any], config: RunnableConfig
    ) -> List[BaseMessage]:
        return await run_in_executor(config, self._current_history, input, config)

    def _update_history(self, run: Run, config: RunnableConfig) -> None:
        """
        退出时，将输入和输出通过chat_memory保存。
        """
        memory = config["configurable"]["memory"]
        store = memory.chat_memory

        # 获得输入
        inputs = run.inputs
        input_val = inputs[self.input_messages_key]
        input_messages = self._get_input_messages(input_val)

        # 获得输出
        output_val = run.outputs
        output_messages = self._get_output_messages(output_val)
        store.add_messages(input_messages + output_messages)

    def _merge_configs(self, *configs: Optional[RunnableConfig]) -> RunnableConfig:
        config = super()._merge_configs(*configs)
        if "configurable" in config:
            memory = self.memory_manager.get_memory_factory(config["configurable"].get("session_id", get_default_session()))
        else:
            memory = self.memory_manager.get_memory_factory(get_default_session())
            config["configurable"] = {}

        config["configurable"]["memory"] = memory
        
        return config
