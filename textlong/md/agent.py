from typing import Annotated, List, Optional, Dict, Any, Union, Callable, Literal
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnablePassthrough
from langchain_core.pydantic_v1 import BaseModel, Field
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langchain.agents.agent import AgentOutputParser, AgentAction, AgentFinish
from langchain.agents.format_scratchpad import format_log_to_str
from langchain.output_parsers import PydanticOutputParser
from langchain.schema.output_parser import StrOutputParser
from langchain.output_parsers import OutputFixingParser
from langchain.prompts import PromptTemplate, ChatPromptTemplate, MessagesPlaceholder
from langchain.tools.render import render_text_description
from .tools import create_chains, create_toolkist
from .prompt import PROMPT_TASK_WRITING
import re

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
        """
        用正则表达式匹配 >->>> 和 <<<-< 标记包围住的字符串并返回；
        如果找到就直接返回。
        """
        pattern = r'>->>>\n(.*?)\n<<<-<'
        matches = re.findall(pattern, text, re.DOTALL)
        return matches if matches else [""]

    @property
    def _type(self) -> str:
        return 'Markdown-Parser'

def create_task_manage_prompt(tools=[], instruction: str=None):
    # 请注意，智谱AI等国内大模型对于pydantic的参数解析并不友好，使用JSON描述参数时会误读
    # 因此，不要使用 render_text_description_and_args 来生成工具描述
    tools_format = render_text_description(tools)

    prompt = PromptTemplate.from_template(instruction or PROMPT_TASK_WRITING).partial(
        outline='暂无',
        detail='暂无',
        tools=tools_format,
        action_format_instructions=_action_parser_format,
    )
    return(prompt)

def add_string(existing: str, new: str):
    return existing + new

class State(TypedDict):
    # 写作任务
    task: str
    # 消息历史
    action: Union[AgentAction, AgentFinish]
    # 写作提纲
    outline: Annotated[list, add_string]
    # 细节扩写
    detail: Annotated[list, add_string]

def create_agent(llm=None, memory=None):
    """
    创建写作智能体。    
    """

    if llm == None:
        from langchain_zhipu import ChatZhipuAI
        llm = ChatZhipuAI()

    chains = create_chains(llm)

    def dispatch_task(state):
        tools = create_toolkist(llm)
        prompt = create_task_manage_prompt(tools, PROMPT_TASK_WRITING)
        input = {
            'task': state['task'],
            'outline': "\n".join(state['outline']) or '暂无',
            'detail': "\n".join(state['detail']) or '暂无',
        }
        
        print("\n", "-"*20, "已有outline:", len(state['outline']))
        print("-"*20, "已有detail:", len(state['detail']), "\n")

        task_chain = prompt | llm
        text = ""
        for chunk in task_chain.stream(input):
            text += chunk.content
            print(chunk.content, end="")
        
        new_parser = OutputFixingParser.from_llm(parser=CotAgentOutputParser(), llm=llm)

        return {"action": new_parser.invoke(text)}

    def create_outline(state):
        outline_chain = chains['outline']
        text = ""
        for chunk in outline_chain.stream({
            'task': state['action'].tool_input['task'],
            'outline': "\n".join(state['outline']) or '暂无',
        }):
            text += chunk.content
            print(chunk.content, end="")

        return {"outline": MarkdownOutputParser().invoke(text)}

    def create_detail(state):
        detail_chain = chains['detail']
        text = ""
        for chunk in detail_chain.stream({
            'task': state['action'].tool_input['task'],
            'outline': "\n".join(state['outline']) or '暂无',
            'detail': "\n".join(state['detail']) or '暂无',
        }):
            text += chunk.content
            print(chunk.content, end="")

        return {'detail': MarkdownOutputParser().invoke(text)}

    def route_tools(
        state: State,
    ) -> Literal['tools', '__end__']:
        action = state['action']
        if action:
            if action.tool == 'create_outline':
                return 'to_create_outline'
            elif action.tool == 'create_detail':
                return 'to_create_detail'
            else:
                return 'QUIT'

    builder = StateGraph(State)

    builder.add_node('dispatch_task', dispatch_task)
    builder.set_entry_point('dispatch_task')
    
    builder.add_node('create_outline', create_outline)
    builder.add_node('create_detail', create_detail)

    builder.add_conditional_edges(
        'dispatch_task',
        route_tools,
        {
            'to_create_outline': 'create_outline',
            'to_create_detail': 'create_detail',
            'QUIT': '__end__'
        },
    )

    builder.add_edge('create_outline', 'dispatch_task')
    builder.add_edge('create_detail', 'dispatch_task')

    return builder.compile(checkpointer=memory)

