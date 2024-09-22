from typing import Union, List, Dict, Any, Callable, Tuple

class BindingManager:
    """
    BindingManager 基类，用于管理绑定相关的功能。
    """

    def __init__(self, runnables: List[Tuple["Runnable", Dict[str, str]]]=None, **kwargs):
        """
        :param runnables: 绑定的 runnable 对象列表
        :param import_mapping: 导入的变量映射，键为本地变量名，值为导入的变量名
        """
        self.runnables = runnables or []

        self._last_input = None
        self._last_output = None

    @property
    def last_input(self):
        return self._last_input

    @property
    def last_output(self):
        return self._last_output

    @property
    def exported_vars(self):
        """
        用于被其他 runnable 对象绑定的变量。
        """
        return {
            "last_input": self.last_input,
            "last_output": self.last_output
        }

    @property
    def imported_vars(self):
        """
        获取所有绑定的 runnable 的 exported_vars 变量。

        如果设定了 binding_map，则将 runnable 中的变量通过 binding_map 进行映射。
        """
        imported_vars = {}
        for runnable, binding_map in self.runnables:
            exported_vars = runnable.exported_vars
            for k, v in exported_vars.items():
                mapping_index = {v: k for k, v in binding_map.items()}
                if k in mapping_index:
                    imported_vars[mapping_index[k]] = v
                else:
                    imported_vars[k] = v

        return imported_vars

    def bind_runnables(self, *runnables: "Runnable", binding_map: Dict[str, str]=None):
        """
        绑定其他 runnable 的字典变量，动态获取 runnable 中的变量，并通过 input_mapping 实现映射转换。
        """
        if isinstance(runnables[-1], dict):
            # 如果最后一个参数使用顺序参数，需要判断最后一个参数是否 binding_map
            # 这可以方便书写类似的情况：
            # obj.bind_runnables(runnable1, runnable2, {"task": "last_input"})
            # 正确识别出最后一个字典是 binding_map 而不是 runnable
            _binding_map = runnables[-1]
            _runnables = runnables[:-1]
        else:
            # 如果最后一个参数使用键值参数，指明 binding_map
            _binding_map = binding_map or {}
            _runnables = runnables

        for runnable in _runnables:
            if runnable not in self.runnables:
                filtered_binding_map = {k: v for k, v in _binding_map.items() if v in runnable.exported_vars}
                self.runnables.append((runnable, filtered_binding_map))
        return self.runnables
