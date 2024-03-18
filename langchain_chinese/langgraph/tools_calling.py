import json
import operator
from typing import Annotated, Sequence, TypedDict, Union

from langchain_core.language_models import LanguageModelLike
from langchain_core.messages import (
    BaseMessage,
    AIMessage,
    HumanMessage,
    ToolMessage
)
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from langgraph.graph import END, MessageGraph
from langgraph.prebuilt.tool_executor import ToolExecutor, ToolInvocation

def create_tools_calling_executor(
    model: LanguageModelLike,
    tools: Union[ToolExecutor, Sequence[BaseTool]],
    runnables: dict = {},
    verbose: bool = False
):
    if isinstance(tools, ToolExecutor):
        tool_executor = tools
        tool_classes = tools.tools
    else:
        tool_executor = ToolExecutor(tools)
        tool_classes = tools

    reasoning_chain = (
        model.bind(tools=[convert_to_openai_tool(t) for t in tool_classes])
    )
    
    def should_continue(messages):
        last_message = messages[-1]
        if "tool_calls" not in last_message.additional_kwargs:
            return "end"
        else:
            tool_call = last_message.additional_kwargs["tool_calls"][0]
            tool_name = tool_call["function"]["name"]
            if verbose:
                print("runnable-name: ", tool_name)
            if tool_name in runnables:
                if verbose:
                    print(f"log: call runnable [{tool_name}]")
                return tool_name
            else:
                if verbose:
                    print(f"log: call tool [{tool_name}]")
                return "tools-callback"

    def _get_actions(messages):
        last_message = messages[-1]
        return (
            [
                ToolInvocation(
                    tool=tool_call["function"]["name"],
                    tool_input=json.loads(tool_call["function"]["arguments"]),
                )
                for tool_call in last_message.additional_kwargs["tool_calls"]
            ],
            [
                tool_call["id"]
                for tool_call in last_message.additional_kwargs["tool_calls"]
            ],
        )

    def call_tool(messages):
        actions, ids = _get_actions(messages)
        responses = tool_executor.batch(actions)
        assert len(actions) == len(responses), "The number of actions and responses should be the same"
        tool_messages = [
            ToolMessage(content=str(response), tool_call_id=id)
            for response, id in zip(responses, ids)
        ]
        return tool_messages

    async def acall_tool(messages):
        actions, ids = _get_actions(messages)
        responses = await tool_executor.abatch(actions)
        tool_messages = [
            ToolMessage(content=str(response), tool_call_id=id)
            for response, id in zip(responses, ids)
        ]
        return tool_messages

    workflow = MessageGraph()

    workflow.add_node("agent", reasoning_chain)
    workflow.add_node("action", RunnableLambda(call_tool, acall_tool))
    for runnable_name in runnables:
        runnable = runnables[runnable_name]
        if not isinstance(runnable, Runnable) and "node" in runnables[runnable_name]:
            runnable = runnables[runnable_name]["node"]
        workflow.add_node(runnable_name, runnable)

    workflow.set_entry_point("agent")

    conditions = {
        "tools-callback": "action",
        "end": END,
    }
    for runnable_name in runnables:
        conditions[runnable_name] = runnable_name
    workflow.add_conditional_edges("agent", should_continue, conditions)

    workflow.add_edge("action", "agent")
    for runnable_name in runnables:
        # 直接结束，除非 runnables 字典中指定了 to 键
        to_node = END
        runnable = runnables[runnable_name]
        if not isinstance(runnable, Runnable) and "to" in runnables[runnable_name]:
            to_node = runnables[runnable_name]["to"]
        workflow.add_edge(runnable_name, to_node)

    return workflow.compile()