from typing import Union, List, Dict, Any, Callable, Tuple

class BindingManager:
    """
    BindingManager 基类，用于管理绑定相关的功能。
    """

    def __init__(self, bindings: Any=None, **kwargs):
        """
        :param binding: 绑定的 (runnable, binding_map)，字典结构，或 Runnable 实例的列表
        """
        self.providers = []
        self.bind_providers(bindings)
        self._provider_dict = {}

    def _convert_bindings(self, bindings: Any=None, raise_message: str=None):
        """
        将 bindings 转换为 (runnable, binding_map) 列表。
        """
        if bindings is None:
            return []

        if isinstance(bindings, list):
            items = bindings
        else:
            items = [bindings]

        bindings = []
        for item in items:
            if not item:
                continue
            if isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], BindingManager):
                if not item[1]:
                    bindings.append((item[0], {}))
                else:
                    if not isinstance(item[1], dict):
                        raise ValueError("binding_map must be a dictionary", item)
                    bindings.append(item)
            elif isinstance(item, BindingManager):
                bindings.append((item, {}))
            elif isinstance(item, dict):
                kk = {k: k if not isinstance(v, Callable) else v for k, v in item.items()}
                bindings.append((PassthroughBinding(**item), kk))
            else:
                if raise_message is None:
                    raise ValueError("bindings must be a list of (runnable, binding_map) tuples or Runnable instances or dict", bindings)
                else:
                    raise ValueError(raise_message, bindings)
        return bindings

    def bind_providers(self, *bindings: Any):
        """
        手工绑定其他 bindings
        """
        message = "binding description must be one of dict, tuple or Runnable instance"
        new_bindings = self._convert_bindings(list(bindings), raise_message=message)
        self.providers.extend(new_bindings)
        return self.providers

    @property
    def provider_dict(self):
        """
        用于被其他 runnable 对象绑定的变量。
        实现绑定变量的传递：将导入的变量合并后作为导出的变量。
        """
        vars = {}
        if self.last_input is not None:
            vars["last_input"] = self.last_input
        if self.last_output is not None:
            vars["last_output"] = self.last_output

        return {**self.consumer_dict, **vars, **self._provider_dict}

    @property
    def consumer_dict(self):
        """
        获取所有绑定的 runnable 的 provider_dict 变量。

        如果设定了 binding_map，则将 runnable 中的变量通过 binding_map 进行映射。

        规则1 如果被绑定 Runnable 的导出变量没有被使用，则按同名导入。
        规则2 如果 binding_map 中映射的值是 str，则使用 provider_dict 中的变量进行映射。
        规则3 如果 binding_map 中映射的值是 Callable，则执行映射函数。

        使用函数扩展时，不会覆盖函数中包含的键值，这实际上提供了 **1:N** 映射的可能性。
        """

        consumer_dict = {}

        for runnable, binding_map in self.providers:
            provider_dict = runnable.provider_dict
            for k, v in provider_dict.items():
                mapping_index = {iv: ik for ik, iv in binding_map.items() if not isinstance(iv, Callable)}
                if k in mapping_index:
                    # 实现规则 2
                    consumer_dict[mapping_index[k]] = v
                else:
                    # 实现规则 1
                    consumer_dict[k] = v
            for k, v in binding_map.items():
                if isinstance(v, Callable):
                    # 实现规则 3
                    consumer_dict[k] = v(provider_dict)

        return consumer_dict

class PassthroughBinding(BindingManager):
    """
    透传字典结构到 provider_dict
    """
    def __init__(self, **kwargs):
        super().__init__(bindings=None)
        self._provider_dict = kwargs

    @property
    def provider_dict(self):
        return self._provider_dict
