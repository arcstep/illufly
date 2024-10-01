from typing import Union, List, Dict, Any, Callable, Tuple

class BindingManager:
    """
    BindingManager 基类，用于管理绑定相关的功能。
    """

    def __init__(self, binding: Any=None, **kwargs):
        """
        :param binding: 绑定的 (runnable, binding_map)，字典结构，或 Runnable 实例的列表
        """
        self.runnables = self._convert_runnables(binding)
        self._exported_vars = {}

    def _convert_runnables(self, bindings: Any=None, raise_message: str=None):
        """
        将 runnables 转换为 (runnable, binding_map) 列表。
        """
        if bindings is None:
            return []

        if isinstance(bindings, list):
            items = bindings
        else:
            items = [bindings]

        runnables = []
        for item in items:
            if isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], BindingManager):
                if not item[1]:
                    runnables.append((item[0], {}))
                else:
                    if not isinstance(item[1], dict):
                        raise ValueError("binding_map must be a dictionary", item)
                    runnables.append(item)
            elif isinstance(item, BindingManager):
                runnables.append((item, {}))
            elif isinstance(item, dict):
                runnables.append((PassthroughBinding(**item), {}))
            else:
                if raise_message is None:
                    raise ValueError("runnables must be a list of (runnable, binding_map) tuples or Runnable instances or dict", bindings)
                else:
                    raise ValueError(raise_message, bindings)
        return runnables

    def bind(self, bindings: Any):
        """
        手工绑定其他 runnables
        """
        message = "binding description must be one of dict, tuple or Runnable instance"
        new_runnables = self._convert_runnables(bindings, raise_message=message)
        self.runnables.extend(new_runnables)
        return self.runnables

    @property
    def exported_vars(self):
        """
        用于被其他 runnable 对象绑定的变量。
        实现绑定变量的传递：将导入的变量合并后作为导出的变量。
        """
        vars = {}
        if self.last_input is not None:
            vars["last_input"] = self.last_input
        if self.last_output is not None:
            vars["last_output"] = self.last_output

        return {**self.imported_vars, **vars, **self._exported_vars}

    @property
    def imported_vars(self):
        """
        获取所有绑定的 runnable 的 exported_vars 变量。

        如果设定了 binding_map，则将 runnable 中的变量通过 binding_map 进行映射。

        规则1 如果被绑定 Runnable 的导出变量没有被使用，则按同名导入。
        规则2 如果 binding_map 中映射的值是 str，则使用 exported_vars 中的变量进行映射。
        规则3 如果 binding_map 中映射的值是 Callable，则执行映射函数。

        使用函数扩展时，不会覆盖函数中包含的键值，这实际上提供了 **1:N** 映射的可能性。
        """

        imported_vars = {}

        for runnable, binding_map in self.runnables:
            exported_vars = runnable.exported_vars
            for k, v in exported_vars.items():
                mapping_index = {iv: ik for ik, iv in binding_map.items() if not isinstance(iv, Callable)}
                if k in mapping_index:
                    # 实现规则 2
                    imported_vars[mapping_index[k]] = v
                else:
                    # 实现规则 1
                    imported_vars[k] = v
            for k, v in binding_map.items():
                if isinstance(v, Callable):
                    # 实现规则 3
                    imported_vars[k] = v(exported_vars)

        return imported_vars

class PassthroughBinding(BindingManager):
    """
    透传字典结构到 exported_vars
    """
    def __init__(self, **kwargs):
        super().__init__(runnables=None)
        self.exported_dict = kwargs

    @property
    def exported_vars(self):
        return self.exported_dict
