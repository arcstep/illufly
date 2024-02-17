class ZhipuAIChat(BaseChatModel):
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
    
    client: ZhipuAI = None
    """访问智谱AI的客户端"""

    model: str = Field(default="glm-3-turbo", alias="model_name")
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
            from zhipuai import ZhipuAI
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
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """实现 ZhiputAI 的同步调用"""
        prompt: List = []
        for message in messages:
            if isinstance(message, AIMessage):
                role = "assistant"
            else:  # For both HumanMessage and SystemMessage, role is 'user'
                role = "user"

            prompt.append({"role": role, "content": message.content})

        # 构造参数序列
        params = self.get_model_kwargs()
        params.update(kwargs)
        params.update({"stream": False})
    
        response = self.client.chat.completions.create(
            messages=prompt,
            **params
        )

        choice = response.choices[0]

        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(content=choice.message.content),
            )],
        )

    # 实现 stream 调用方法
    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """实现 ZhiputAI 的事件流调用"""
        prompt: List = []
        for message in messages:
            if isinstance(message, AIMessage):
                role = "assistant"
            else:  # For both HumanMessage and SystemMessage, role is 'user'
                role = "user"

            prompt.append({"role": role, "content": message.content})

        # 使用流输出
        # 构造参数序列
        params = self.get_model_kwargs()
        params.update(kwargs)
        params.update({"stream": True})
    
        response = self.client.chat.completions.create(
            messages=prompt,
            **params
        )

        for chunk in response:
            choice = chunk.choices[0]
            yield ChatGenerationChunk(
                message=AIMessageChunk(content=choice.delta.content),
            )