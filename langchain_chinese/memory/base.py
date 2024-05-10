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
        # 提取记忆 _enter_memory / _aenter_memory
        history_chain: Runnable = RunnableLambda(
            self._enter_memory, self._aenter_memory
        ).with_config(run_name="load_history")
        messages_key = history_messages_key or input_messages_key
        if messages_key:
            history_chain = RunnablePassthrough.assign(
                **{messages_key: history_chain}
            ).with_config(run_name="insert_history")

        # 写入记忆 _exit_memory
        bound = (
            history_chain | runnable.with_listeners(on_end=self._exit_memory)
        ).with_config(run_name="WithMemoryBinding")

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

            fields: Dict = {}
            if self.input_messages_key and self.history_messages_key:
                fields[self.input_messages_key] = (
                    Union[str, BaseMessage, Sequence[BaseMessage]],
                    ...,
                )
            elif self.input_messages_key:
                fields[self.input_messages_key] = (Sequence[BaseMessage], ...)
            else:
                fields["__root__"] = (Sequence[BaseMessage], ...)
            return create_model(
                "RunnableWithChatHistoryInput",
                **fields,
            )
        else:
            return super_schema

    def _get_input_messages(
        self, input_val: Union[str, BaseMessage, Sequence[BaseMessage]]
    ) -> List[BaseMessage]:
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
        from langchain_core.messages import BaseMessage

        # 如果output_val是字典就取其中的output键或指定名字的键
        if isinstance(output_val, dict):
            output_val = output_val[self.output_messages_key or "output"]

        if isinstance(output_val, str):
            from langchain_core.messages import AIMessage

            return [AIMessage(content=output_val)]
        elif isinstance(output_val, BaseMessage):
            return [output_val]
        elif isinstance(output_val, (list, tuple)):
            return list(output_val)
        else:
            raise ValueError()

    def _enter_memory(self, input: Any, config: RunnableConfig) -> List[BaseMessage]:
        memory = config["configurable"]["memory"]
        # 提取记忆中应当插入到提示语中的部份
        if self.history_messages_key:
            return memory.buffer_as_messages
        else:
            input_val = (
                input if not self.input_messages_key else input[self.input_messages_key]
            )
            return memory.buffer_as_messages + self._get_input_messages(input_val)

    async def _aenter_memory(
        self, input: Dict[str, Any], config: RunnableConfig
    ) -> List[BaseMessage]:
        return await run_in_executor(config, self._enter_memory, input, config)

    def _exit_memory(self, run: Run, config: RunnableConfig) -> None:
        memory = config["configurable"]["memory"]
        hist = memory.chat_memory

        # Get the input messages
        inputs = load(run.inputs)
        input_val = inputs[self.input_messages_key or "input"]
        input_messages = self._get_input_messages(input_val)

        # If historic messages were prepended to the input messages, remove them to
        # avoid adding duplicate messages to history.
        if not self.history_messages_key:
            input_messages = input_messages[len(hist.messages) :]

        # Get the output messages
        output_val = load(run.outputs)
        output_messages = self._get_output_messages(output_val)
        hist.add_messages(input_messages + output_messages)
        
        # print("_exit_memory", hist)

    def _merge_configs(self, *configs: Optional[RunnableConfig]) -> RunnableConfig:
        config = super()._merge_configs(*configs)
        expected_keys = [field_spec.id for field_spec in self.history_factory_config]

        configurable = config.get("configurable", {})

        # 如果没有提供 history_factory_config 中要求的键就抛出异常
        missing_keys = set(expected_keys) - set(configurable.keys())
        if missing_keys:
            example_input = {self.input_messages_key: "foo"}
            example_configurable = {
                missing_key: "[your-value-here]" for missing_key in missing_keys
            }
            example_config = {"configurable": example_configurable}
            raise ValueError(
                f"Missing keys {sorted(missing_keys)} in config['configurable'] "
                f"Expected keys are {sorted(expected_keys)}."
                f"When using via .invoke() or .stream(), pass in a config; "
                f"e.g., chain.invoke({example_input}, {example_config})"
            )

        parameter_names = _get_parameter_names(self.memory_manager.get_longterm_memory_factory)

        if len(expected_keys) == 1:
            # 如果configurable中只有一个参数，无论其是否session_id，都当作位置参数传递给记忆体
            # 所有记忆体的实现中，都应当将第1个位置参数当作session_id使用
            memory = self.memory_manager.get_shorterm_memory(configurable[expected_keys[0]])
        else:
            # 如果有configurable中有多个参数，就当作键值参数传递给记忆体
            # 在记忆体的实现中，都应当支持按匹配的键值参数来保存和提取记忆历史
            # 这在一定程度上提供了定制记忆体的可能性
            if set(expected_keys) != set(parameter_names):
                raise ValueError(
                    f"Expected keys {sorted(expected_keys)} do not match parameter "
                    f"names {sorted(parameter_names)} of memory_writing."
                )

            memory = self.memory_manager.get_shorterm_memory(
                **{key: configurable[key] for key in expected_keys}
            )
        config["configurable"]["memory"] = memory
        # print("_merge_configs:", memory)
        
        return config


def _get_parameter_names(callable_: GetSessionHistoryCallable) -> List[str]:
    """提取 callable_ 的键值参数"""
    sig = inspect.signature(callable_)
    return list(sig.parameters.keys())
