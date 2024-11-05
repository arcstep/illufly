
import matplotlib.pyplot as plt

from .python_code import PythonAgent

class MatplotAgent(PythonAgent):
    """
    使用 matplotlib 绘制图表的 Agent。
    """

    def __init__(self, *args, template_id: str=None, **kwargs):
        self.template_id = template_id or "CODE/Matplot"

        # 生成作为工具被使用时的功能描述
        _tool_params = kwargs.pop("tool_params", {
            "question": "细致描述图表绘制任务的需求描述",
        })
        super().__init__(*args, tool_params=_tool_params, **kwargs)
