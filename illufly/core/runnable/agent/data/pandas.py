from .python_code import PythonAgent

class PandasAgent(PythonAgent):
    """
    对所提供的 pandas 数据集做分析和处理。
    """

    def __init__(self, *args, template_id: str=None, **kwargs):
        self.template_id = template_id or "CODE/Pandas"

        # 生成作为工具被使用时的功能描述
        _tool_params = kwargs.pop("tool_params", {
            "question": "细致描述数据分析任务的需求描述",
        })
        super().__init__(*args, tool_params=_tool_params, **kwargs)

