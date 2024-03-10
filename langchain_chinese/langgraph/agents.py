import json
import operator
from typing import Annotated, Sequence, TypedDict, Union

from langchain_core.language_models import LanguageModelLike
from langchain_core.messages import (
    BaseMessage,
    AIMessage,
    HumanMessage,
    FunctionMessage,
    ToolMessage
)
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from langgraph.graph import END, StateGraph
from langgraph.prebuilt.tool_executor import ToolExecutor, ToolInvocation

def create_tool_calling_executor(
	model: LanguageModelLike, tools: Union[ToolExecutor, Sequence[BaseTool]]
):
	if isinstance(tools, ToolExecutor):
		tool_executor = tools
		tool_classes = tools.tools
	else:
		tool_executor = ToolExecutor(tools)
		tool_classes = tools
	model = model.bind(tools=[convert_to_openai_tool(t) for t in tool_classes])
	
	class AgentState(TypedDict):
		messages: Annotated[Sequence[BaseMessage], operator.add]

	def should_continue(state: AgentState):
		messages = state["messages"]
		last_message = messages[-1]
		if "tool_calls" not in last_message.additional_kwargs:
			return "end"
		else:
			return "continue"

	def call_model(state: AgentState):
		messages = state["messages"]
		message = AIMessage(content="")
		for chunk in model.stream(messages):
			message.content += chunk.content
			if chunk.additional_kwargs:
				message.additional_kwargs = chunk.additional_kwargs
		return {"messages": [message]}

	async def acall_model(state: AgentState):
		messages = state["messages"]
		message = AIMessage(content="")
		async for chunk in model.astream(messages):
			message.content += chunk.content
			if chunk.additional_kwargs:
				message.additional_kwargs = chunk.additional_kwargs
		return {"messages": [message]}

	def _get_actions(state: AgentState):
		messages = state["messages"]
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

	def call_tool(state: AgentState):
		actions, ids = _get_actions(state)
		responses = tool_executor.batch(actions)
		assert len(actions) == len(responses), "The number of actions and responses should be the same"
		tool_messages = [
			ToolMessage(content=str(response), tool_call_id=id)
			for response, id in zip(responses, ids)
		]
		return {"messages": tool_messages}

	async def acall_tool(state: AgentState):
		actions, ids = _get_actions(state)
		responses = await tool_executor.abatch(actions)
		tool_messages = [
			ToolMessage(content=str(response), tool_call_id=id)
			for response, id in zip(responses, ids)
		]
		return {"messages": tool_messages}

	workflow = StateGraph(AgentState)

	workflow.add_node("agent", RunnableLambda(call_model, acall_model))
	workflow.add_node("action", RunnableLambda(call_tool, acall_tool))

	workflow.set_entry_point("agent")

	workflow.add_conditional_edges(
		"agent",
		should_continue,
		{
			"continue": "action",
			"end": END,
		},
	)

	workflow.add_edge("action", "agent")

	return workflow.compile()