from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import (
    BaseChatModel,
    generate_from_stream,
)
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    BaseMessageChunk,
    HumanMessage,
    HumanMessageChunk,
    ToolMessage,
    ToolMessageChunk,
    SystemMessage,
    SystemMessageChunk,
    ChatMessage,
    ChatMessageChunk,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from typing import Type, Any, Mapping, Dict, Iterator, List, Optional, cast

from langchain_core.pydantic_v1 import BaseModel, Field, root_validator

def _convert_dict_to_message(_dict: Mapping[str, Any]) -> BaseMessage:
    """Convert a dictionary to a LangChain message.

    Args:
        _dict: The dictionary.

    Returns:
        The LangChain message.
    """
    role = _dict.get("role")
    if role == "user":
        return HumanMessage(content=_dict.get("content", ""))
    elif role == "assistant":
        # Fix for azure
        # Also OpenAI returns None for tool invocations
        content = _dict.get("content", "") or ""
        additional_kwargs: Dict = {}
        if tool_calls := _dict.get("tool_calls"):
            additional_kwargs["tool_calls"] = tool_calls
        return AIMessage(content=content, additional_kwargs=additional_kwargs)
    elif role == "system":
        return SystemMessage(content=_dict.get("content", ""))
    elif role == "tool":
        additional_kwargs = {}
        return ToolMessage(
            content=_dict.get("content", ""),
            tool_call_id=_dict.get("tool_call_id"),
            additional_kwargs=additional_kwargs,
        )
    else:
        return ChatMessage(content=_dict.get("content", ""), role=role)

def _convert_message_to_dict(message: BaseMessage) -> dict:
    """Convert a LangChain message to a dictionary.

    Args:
        message: The LangChain message.

    Returns:
        The dictionary.
    """
    message_dict: Dict[str, Any]
    if isinstance(message, ChatMessage):
        message_dict = {"role": message.role, "content": message.content}
    elif isinstance(message, HumanMessage):
        message_dict = {"role": "user", "content": message.content}
    elif isinstance(message, AIMessage):
        message_dict = {"role": "assistant", "content": message.content}
        if "tool_calls" in message.additional_kwargs:
            message_dict["tool_calls"] = message.additional_kwargs["tool_calls"]
            # If tool calls only, content is None not empty string
            if message_dict["content"] == "":
                message_dict["content"] = None
    elif isinstance(message, SystemMessage):
        message_dict = {"role": "system", "content": message.content}
    elif isinstance(message, ToolMessage):
        message_dict = {
            "role": "tool",
            "content": message.content,
            "tool_call_id": message.tool_call_id,
        }
    else:
        raise TypeError(f"Got unknown type {message}")
    if "name" in message.additional_kwargs:
        message_dict["name"] = message.additional_kwargs["name"]
    return message_dict

def _convert_delta_to_message_chunk(
    _dict: Mapping[str, Any], default_class: Type[BaseMessageChunk]
) -> BaseMessageChunk:
    role = cast(str, _dict.get("role"))
    content = cast(str, _dict.get("content") or "")
    additional_kwargs: Dict = {}
    if _dict.get("tool_calls"):
        additional_kwargs["tool_calls"] = _dict["tool_calls"]

    if role == "user" or default_class == HumanMessageChunk:
        return HumanMessageChunk(content=content)
    elif role == "assistant" or default_class == AIMessageChunk:
        return AIMessageChunk(content=content, additional_kwargs=additional_kwargs)
    elif role == "system" or default_class == SystemMessageChunk:
        return SystemMessageChunk(content=content)
    elif role == "tool" or default_class == ToolMessageChunk:
        return ToolMessageChunk(content=content, tool_call_id=_dict["tool_call_id"])
    elif role or default_class == ChatMessageChunk:
        return ChatMessageChunk(content=content, role=role)
    else:
        return default_class(content=content)  # type: ignore

class ChatZhipuAI(BaseChatModel):
    """支持最新的智谱API"""

    @property
    def lc_secrets(self) -> Dict[str, str]:
        return {"zhipuai_api_key": "ZHIPUAI_API_KEY"}

    @property
    def _llm_type(self) -> str:
        """Return the type of chat model."""
        return "zhipuai"

    @property
    def lc_attributes(self) -> Dict[str, Any]:
        attributes: Dict[str, Any] = {}

        if self.model:
            attributes["model"] = self.model

        if self.streaming:
            attributes["streaming"] = self.streaming

        if self.return_type:
            attributes["return_type"] = self.return_type

        return attributes

    @classmethod
    def get_lc_namespace(cls) -> List[str]:
        """Get the namespace of the langchain object."""
        return ["langchain", "chat_models", "ZhipuAI"]
    
    client: Any = None
    """访问智谱AI的客户端"""
    
    api_key: str = None

    model: str = Field(default="glm-3-turbo")
    """所要调用的模型编码"""

    request_id: Optional[str] = None
    """
    由用户端传参，需保证唯一性；用于区分每次请求的唯一标识，用户端不传时平台会默认生成。
    """
    
    do_sample: Optional[bool] = None
    """
    do_sample 为 true 时启用采样策略;
    do_sample 为 false 时采样策略 temperature、top_p 将不生效
    """

    temperature: Optional[float] = None
    """
    采样温度，控制输出的随机性，必须为正数；
    取值范围是：
      - (0.0,1.0]，不能等于 0，默认值为 0.95,值越大，会使输出更随机，更具创造性；
      - 值越小，输出会更加稳定或确定；

    建议您根据应用场景调整 top_p 或 temperature 参数，但不要同时调整两个参数。
    """

    top_p: Optional[float] = None
    """
    用温度取样的另一种方法，称为核取样：
    取值范围是：(0.0, 1.0) 开区间，不能等于 0 或 1，默认值为 0.7。
    模型考虑具有 top_p 概率质量tokens的结果。

    例如：0.1 意味着模型解码器只考虑从前 10% 的概率的候选集中取tokens
    建议您根据应用场景调整 top_p 或 temperature 参数，但不要同时调整两个参数。
    """

    max_tokens: Optional[int] = None
    """模型输出最大tokens"""

    stop: Optional[List[str]] = None
    """
    模型在遇到stop所制定的字符时将停止生成，目前仅支持单个停止词，格式为["stop_word1"]    
    """

    tools: List[Any] = None
    """
    可供模型调用的工具列表,tools字段会计算 tokens ，同样受到tokens长度的限制。
    """

    tool_choice: Optional[str] = "auto"
    """
    用于控制模型是如何选择要调用的函数，仅当工具类型为function时补充。默认为auto，当前仅支持auto。
    """

    @classmethod
    def valid_params(cls):
        """
        ZhipuAI只接受这些参数。另外，stream参数根据使用invoke方法还是stream方法来设定，而不是在对象构建时提供。
        """
        return [
            "model",
            "request_id",
            "do_sample",
            "stream",
            "temperature",
            "top_p",
            "max_tokens",
            "stop",
            "tools",
            "tool_choice",
        ]
        
    # 获得模型调用参数
    def get_model_kwargs(self):
        params = {}
        for attr, value in self.__dict__.items():
            if attr in self.__class__.valid_params() and value is not None:
                params[attr] = value
        return params

    @root_validator()
    def validate_environment(cls, values: Dict) -> Dict:
        try:
            # 声明 ZhipuAI 的客户端
            from zhipuai_pydantic_v1 import ZhipuAI
            if values["api_key"] is not None:
                values["client"] =  ZhipuAI(api_key=values["api_key"])
            else:
                values["client"] =  ZhipuAI()
        except ImportError:
            raise RuntimeError(
                "Could not import zhipuai package. "
                "Please install it via 'pip install zhipuai'"
            )
        return values

    # 实现 invoke 调用方法
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        stream: Optional[bool] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """实现 ZhiputAI 的同步调用"""
        prompt = [_convert_message_to_dict(message) for message in messages]

        # 构造参数序列
        params = self.get_model_kwargs()
        params.update(kwargs)
        params.update({"stream": False})
        if stop is not None:
            params.update({"stop": stop})
    
        response = self.client.chat.completions.create(
            messages=prompt,
            **params
        )

        generations = []
        if not isinstance(response, dict):
            response = response.dict()
        for res in response["choices"]:
            message = _convert_dict_to_message(res["message"])
            generation_info = dict(finish_reason=res.get("finish_reason"))
            gen = ChatGeneration(
                message=message,
                generation_info=generation_info,
            )
            generations.append(gen)
        token_usage = response.get("usage", {})
        llm_output = {
            "id": response.get("id"),
            "created": response.get("created"),
            "token_usage": token_usage,
            "model_name": self.model,
        }
        return ChatResult(generations=generations, llm_output=llm_output)

    # 实现 stream 调用方法
    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """实现 ZhiputAI 的事件流调用"""
        prompt = [_convert_message_to_dict(message) for message in messages]

        # 使用流输出
        # 构造参数序列
        params = self.get_model_kwargs()
        params.update(kwargs)
        params.update({"stream": True})
        if stop is not None:
            params.update({"stop": stop})
    
        response = self.client.chat.completions.create(
            messages=prompt,
            **params
        )

        default_chunk_class = AIMessageChunk
        for chunk in response:
            if not isinstance(chunk, dict):
                chunk = chunk.dict()
            if len(chunk["choices"]) == 0:
                continue
            choice = chunk["choices"][0]
            chunk = _convert_delta_to_message_chunk(
                choice["delta"], default_chunk_class
            )
            generation_info = {}
            if finish_reason := choice.get("finish_reason"):
                generation_info["finish_reason"] = finish_reason
            default_chunk_class = chunk.__class__
            chunk = ChatGenerationChunk(
                message=chunk, generation_info=generation_info or None
            )
            if run_manager:
                run_manager.on_llm_new_token(chunk.text, chunk=chunk)
            yield chunk
