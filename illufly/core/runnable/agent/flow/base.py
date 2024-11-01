import re
import uuid
from typing import List, Union, Generator, AsyncGenerator, Callable
from .....io import EventBlock, NewLineBlock
from .....utils import minify_text, filter_kwargs, raise_invalid_params
from ...selector import Selector, End
from ..base import BaseAgent

class FlowAgent(BaseAgent):
    @classmethod
    def allowed_params(cls):
        return {
            "max_steps": "最大步骤数",
            **BaseAgent.allowed_params(),
        }

    def __init__(self, *agents, max_steps: int=None, **kwargs):
        """
        初始化 FlowAgent

        agents 是一个字典列表，键值是流程中的名称，值是一个 BaseAgent 或 Selector 实例。
        也可以直接传入一个 BaseAgent 列表，由初始化函数自动生成相应的键名。
        """
        raise_invalid_params(kwargs, self.allowed_params())
        super().__init__(**filter_kwargs(kwargs, self.allowed_params()))

        self.max_steps = max_steps or 20

        self.thread_id = None
        self.task = None
        self.agents = []
        self.agents_index = {}

        for i, agent in enumerate(agents):
            _node_name = None
            _agent = None
            if isinstance(agent, dict):
                _node_name = list(agent.keys())[0]
                _agent = self.convert_base_agent(list(agent.values())[0])
            else:
                _agent = self.convert_base_agent(agent)
                if _agent.name in self.agents_index:
                    _node_name = f"{_agent.name}-{len(self.agents_index)}"
                else:
                    _node_name = _agent.name

            self.agents.append((_node_name, _agent))
            self.agents_index[_node_name] = (i, _agent)

    def __repr__(self):
        return f"FlowAgent({[agent[0] for agent in self.agents]})"

    def convert_base_agent(self, agent):
        if isinstance(agent, (BaseAgent, Selector, End)):
            return agent
        elif isinstance(agent, Callable):
            return BaseAgent(name=agent.__name__, func=agent)
        else:
            raise ValueError("agent must be a BaseAgent, Selector or Callable")

    def get_agent(self, name):
        return self.agents_index.get(name, (None, None))[1]

    def begin_call(self, args):
        """
        开始执行的回调方法。
        """
        self.thread_id = str(uuid.uuid4())
        self.task = args[0] if args else None
        return args

    def end_call(self):
        """
        结束执行的回调方法。
        """
        pass

    def is_end(self, agent):
        if isinstance(agent, str):
            return agent.lower() == "__end__"
        elif isinstance(agent, BaseAgent):
            return agent.name.lower() == "__end__"

        raise ValueError("agent must be a str or BaseAgent", agent)

    def call(self, *args, **kwargs):
        """
        执行智能体管道。
        """

        # 初始化当前节点信息
        (current_node_name, current_agent) = self.agents[0]
        current_index = 0

        # 初始化调用参数
        current_kwargs = kwargs

        # 初始化总步数
        steps_count = 1

        # 开始回调
        current_args = self.begin_call(args)

        while(steps_count < self.max_steps):
            # 从 current_node_name 获得 agent 和 当前 index
            (current_index, selected_agent) = self.agents_index.get(current_node_name, (None, None))
            if current_index is None:
                yield EventBlock("warn", f"节点 {current_node_name} 不存在")
                break

            # 如果 selected_agent 是一个选择器
            if isinstance(selected_agent, Selector):
                # 如果是选择器，就执行一次 select 方法
                selected_agent.select()
                # 更新当前节点的名称 current_node_name
                if isinstance(selected_agent.selected, str):
                    current_node_name = selected_agent.selected

                    # 如果已经到了 __End__  节点，就退出
                    if current_node_name.lower() == "__end__":
                        yield EventBlock("info", f"到达 __End__ 节点，结束")
                        break

                    (current_index, selected_agent) = self.agents_index.get(current_node_name, (None, None))
                    if current_index is None:
                        yield EventBlock("warn", f"节点 {current_node_name} 不存在")
                        break
                else:
                    current_node_name = selected_agent.selected.name
            elif isinstance(selected_agent, End):
                yield EventBlock("info", f"到达 __End__ 节点，结束")
                break

            # 广播节点信息给 handlers
            info = self._get_node_info(current_index + 1, current_node_name)
            yield EventBlock("agent", info)

            # 执行当前节点的 call 方法
            call_resp = selected_agent.selected.call(*current_args, **current_kwargs)
            if isinstance(call_resp, Generator):
                yield from call_resp

            # 分析当前节点的输出
            if selected_agent.selected.last_output:
                # 如果节点已经有了最终的输出，就保存到 FlowAgent 的 last_output 属性中
                self._last_output = selected_agent.selected.last_output

            # 构造下一次调用的参数
            current_args = [selected_agent.selected]

            if (current_index + 1) >= len(self.agents):
                # 如果已经超出最后一个节点，就结束
                yield EventBlock("warn", f"超出最后一个节点，结束")
                break
            else:
                # 否则继续处理下一个节点
                (current_node_name, current_agent) = self.agents[current_index + 1]

            # 总步数递增
            steps_count += 1

        # 结束回调
        self.end_call()

        yield EventBlock("info", f"执行完毕，所有节点运行 {steps_count} 步")

    async def async_call(self, *args, **kwargs):
        """
        执行智能体管道。
        """

        # 初始化当前节点信息
        (current_node_name, current_agent) = self.agents[0]
        current_index = 0

        # 初始化调用参数
        current_kwargs = kwargs

        # 初始化总步数
        steps_count = 1

        # 开始回调
        current_args = self.begin_call(args)

        while(steps_count < self.max_steps):
            # 从 current_node_name 获得 agent 和 当前 index
            (current_index, selected_agent) = self.agents_index.get(current_node_name, (None, None))
            if current_index is None:
                yield EventBlock("warn", f"节点 {current_node_name} 不存在")
                break

            # 如果 selected_agent 是一个选择器
            if isinstance(selected_agent, Selector):
                # 如果是选择器，就执行一次 select 方法
                selected_agent.select()
                # 更新当前节点的名称 current_node_name
                if isinstance(selected_agent.selected, str):
                    current_node_name = selected_agent.selected

                    # 如果已经到了 __End__  节点，就退出
                    if current_node_name.lower() == "__end__":
                        yield EventBlock("info", f"到达 __End__ 节点，结束")
                        break

                    (current_index, selected_agent) = self.agents_index.get(current_node_name, (None, None))
                    if current_index is None:
                        yield EventBlock("warn", f"节点 {current_node_name} 不存在")
                        break
                else:
                    current_node_name = selected_agent.selected.name
            elif isinstance(selected_agent, End):
                yield EventBlock("info", f"到达 __End__ 节点，结束")
                break

            # 广播节点信息给 handlers
            info = self._get_node_info(current_index + 1, current_node_name)
            yield EventBlock("agent", info)

            # 执行当前节点的 call 方法
            call_resp = await selected_agent.selected.async_call(*current_args, **current_kwargs)
            if isinstance(call_resp, AsyncGenerator):
                async for block in call_resp:
                    yield block

            # 分析当前节点的输出
            if selected_agent.selected.last_output:
                # 如果节点已经有了最终的输出，就保存到 FlowAgent 的 last_output 属性中
                self._last_output = selected_agent.selected.last_output

            # 构造下一次调用的参数
            current_args = [selected_agent.selected]

            if (current_index + 1) >= len(self.agents):
                # 如果已经超出最后一个节点，就结束
                yield EventBlock("warn", f"超出最后一个节点，结束")
                break
            else:
                # 否则继续处理下一个节点
                (current_node_name, current_agent) = self.agents[current_index + 1]

            # 总步数递增
            steps_count += 1

        # 结束回调
        self.end_call()

        yield EventBlock("info", f"执行完毕，所有节点运行 {steps_count} 步")


    def _get_node_info(self, index, node_name):
        return f">>> Node {index}: {node_name}"

