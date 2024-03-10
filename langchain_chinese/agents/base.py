from typing import List, Optional, Dict, Any, Union, Callable
from langchain_core.runnables import RunnablePassthrough
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain.agents.agent import AgentOutputParser, AgentAction, AgentFinish
from langchain.agents.format_scratchpad import format_log_to_str
from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate
from langchain.tools.render import render_text_description
from .prompt import PROMPT_COT, PROMPT_REACT

class Action(BaseModel):
    name: str = Field(
        description="The name of tool or action: FINISH or Other tool names."
        )
    args: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Parameters of tool or action are composed of names and values."
        )

# 解析Action
_action_output_parser = PydanticOutputParser(pydantic_object=Action)
_action_parser_format = _action_output_parser.get_format_instructions()

class ReasonOutputParser(AgentOutputParser):
    """解析单个动作的智能体action和输入参数。
    """

    def parse(self, text: str) -> Union[AgentAction, AgentFinish]:
        action: Action = _action_output_parser.invoke(text)
        name: Optional[str] = action.name
        args: Optional[Dict[str, Any]] = action.args if text is not None else "No Args"
        log: str = text if text is not None else ""

        if name == "FINISH":
            return AgentFinish(args, log)
        elif name is not None:
            return AgentAction(name, args, log)

    @property
    def _type(self) -> str:
        return "Chain-of-Thought"

def _prompt_creator(prompt: str) -> Callable[[List[str]], str]:
    def creator(tools: List[str]) -> str:
        # 请注意，智谱AI等国内大模型对于pydantic的参数解析并不友好，使用JSON描述参数时会误读
        # 因此，不要使用 render_text_description_and_args 来生成工具描述
        tools_format = render_text_description(tools)

        template = PromptTemplate.from_template(prompt)
        return template.partial(
            tools=tools_format,
            action_format_instructions=_action_parser_format,
        )

    return creator

# 基于 ReAct / CoT 的智能体
def create_reason_agent(llm: Any, prompt: Optional[str] = None, tools: List[str] = []) -> Any:
    prompt_creator = _prompt_creator(PROMPT_COT)
    if prompt is not None:
        prompt_creator = _prompt_creator(prompt)

    agent = (
        RunnablePassthrough.assign(
            agent_scratchpad=lambda x: format_log_to_str(x["intermediate_steps"])
        )
        | prompt_creator(tools)
        | llm
        | ReasonOutputParser()
    )

    return agent