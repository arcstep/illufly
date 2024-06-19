from typing import Annotated, List, Optional, Dict, Any, Union, Callable, Literal
from typing_extensions import TypedDict
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain.agents.agent import AgentOutputParser, AgentAction, AgentFinish
from langchain.agents.format_scratchpad import format_log_to_str
from langchain.output_parsers import PydanticOutputParser
from ..utils import extract_text

class Action(BaseModel):
    name: str = Field(
        description='The name of tool or action: FINISH or Other tool names.'
        )
    args: Optional[Dict[str, Any]] = Field(
        default=None,
        description='Parameters of tool or action are composed of names and values.'
        )

# 解析Action
_action_output_parser = PydanticOutputParser(pydantic_object=Action)
_action_parser_format = _action_output_parser.get_format_instructions()

class CotAgentOutputParser(AgentOutputParser):
    """
    解析单个动作的智能体`Action`和输入参数。
    """

    def parse(self, text: str) -> Union[AgentAction, AgentFinish]:
        action: Action = _action_output_parser.invoke(text)
        name: Optional[str] = action.name
        args: Optional[Dict[str, Any]] = action.args if text is not None else 'No Args'
        log: str = text if text is not None else ''

        if name == 'FINISH':
            return AgentFinish(args, log)
        elif name is not None:
            return AgentAction(name, args, log)

    @property
    def _type(self) -> str:
        return 'Chain-of-Thought'

class MarkdownOutputParser(AgentOutputParser):
    """
    从`>->>>`和`<<<-<`标记包围的字符串解析`Markdown`内容。
    """

    def parse(self, text: str) -> List[str]:
        return [extract_text(text)] or [""]

    @property
    def _type(self) -> str:
        return 'Markdown-Parser'
