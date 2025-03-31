from typing import Union, List, Dict, Any, Callable, Tuple
import copy

class BindingManager:
    """
    BindingManager 基类，用于管理绑定相关的功能。

    关于动态绑定：有时仅希望短暂维持绑定关系，例如在调用函数中临时建立的绑定关系，希望每次重置。
    这与实例声明时希望长期建立的绑定关系不同，称为动态绑定。

    绑定机制的限制：
    1. 不能重复绑定，重复绑定将被忽略。
    2. 不能扩散传播 None 的 provider 键值。
    """
    @classmethod
    def allowed_params(cls):
        """
        返回当前可用的参数列表。
        """
        return {
            "providers": "实例的 consumer_dict 属性由 providers 列表中每个 Runnable 的 provider_dict 属性提供",
            "consumers": "实例的 provider_dict 属性将被 consumers 列表中每个 Runnable 引用",
            "dynamic_providers": "如果实例在不同周期中重复使用，可能会希望先在绑定前先清除旧的绑定，此时就应该使用动态绑定，即执行 bind_provider 时提供 dynamic=True 参数",
            "lazy_binding_map": "有时你无法确定被哪个对象绑定，但能确定绑定映射，此时就可以使用 lazy_binding_map 参数，在绑定时由对方根据该参数进行绑定",
        }

    def __init__(
        self,
        providers: List[Tuple[Any, Dict]]=None,
        consumers: List[Tuple[Any, Dict]]=None,
        dynamic_providers: List[Tuple[Any, Dict]]=None,
        lazy_binding_map: Dict=None
    ):
        """
        :param binding: 绑定的 (runnable, binding_map)，字典结构，或 Runnable 实例的列表
        """
        self.providers = providers or []
        self.consumers = consumers or []
        self.dynamic_providers = dynamic_providers or []

        # lazy_binding_map 可用于被绑定时默认采纳的 binding_map
        self.lazy_binding_map = lazy_binding_map or {}

    @property
    def provider_dict(self):
        """
        用于被其他 runnable 对象绑定的变量。
        实现绑定变量的传递：将导入的变量合并后作为导出的变量。

        需要注意的是，值为 None 的绑定变量不会被传递；
        但仅针对明确的 None 值，真是因为真的希望传递空值，所以 ""、[] 等非 None 空值仍然会被传递。
        """
        return {k: v for k, v in self.consumer_dict.items() if v is not None}

    def clear_dynamic_providers(self):
        """
        清除所有动态绑定的 providers
        """
        self.dynamic_providers = []

    def _convert_binding(self, runnable: "Runnable"=None, binding_map: Dict=None):
        """
        将 binding 转换为 (runnable, binding_map) 标准形式。
        """
        if not runnable and not binding_map:
            raise ValueError("runnable and binding_map cannot be both empty")

        # 这里做一个语法糖转换，如果传入的是一个字典，则表示 binding_map，runnable 为 None        
        if isinstance(runnable, dict) and binding_map is None:
            binding_map = copy.deepcopy(runnable)
            runnable = None

        binding_map = binding_map or self.lazy_binding_map
        runnable = runnable or PassthroughBinding(binding_map=binding_map)

        if not isinstance(runnable, BindingManager):
            raise ValueError("runnable must be a Runnable instance", runnable)
        if not isinstance(binding_map, dict):
            raise ValueError("binding_map must be a dictionary", binding_map)

        return (runnable, binding_map)

    def bind_provider(self, runnable: "Runnable"=None, binding_map: Dict=None, dynamic: bool=False):
        """
        绑定其他 providers 以便使用其输出字典。

        可以按 binding 中的映射规则绑定到 Runnable 实例，然后动态获取值；
        也可以直接从指定 dict 结构中获取值。

        动态绑定：
        如果 dynamic 为 True，则清除所有动态绑定的 providers，并添加新的动态绑定。
        """
        (provider_runnable, binding_map) = self._convert_binding(runnable, binding_map)

        if not isinstance(provider_runnable, BindingManager):
            raise ValueError("provider runnable must be a Runnable instance", provider_runnable)

        if provider_runnable.name in [r[0].name for r in self.providers]:
            # 如果已经绑定则忽略，不重复绑定
            return

        if dynamic:
            self.clear_dynamic_providers()
            self.dynamic_providers.append((provider_runnable, binding_map))
        else:
            self.providers.append((provider_runnable, binding_map))
            provider_runnable.consumers.append((self, binding_map))

    def bind_consumer(self, runnable: "Runnable", binding_map: Dict=None, dynamic: bool=False):
        """
        将自身绑定给 consumers 以便将输出字典提供其使用。

        与 bind_provider 不同，不存在将自己的输出字典传递给一个字典的情况，因此被绑定的消费者 runnable 不能为空。
        """
        if not isinstance(runnable, BindingManager):
            raise ValueError("consumer runnable must be a Runnable instance", runnable)
        runnable.bind_provider(self, binding_map, dynamic=dynamic)

    @property
    def consumer_dict(self):
        """
        获取所有绑定的 runnable 的 provider_dict 变量。

        如果设定了 binding_map，则将 runnable 中的变量通过 binding_map 进行映射。

        规则1 如果被绑定 Runnable 的导出变量没有被使用，则按同名导入。
        规则2 如果 binding_map 中映射的值是 str，则使用 provider_dict 中的变量进行映射。
        规则3 如果 binding_map 中映射的值是 Callable，则执行映射函数。
        规则4 如果 binding_map 中映射的值是 None 则放弃映射。

        使用函数扩展时，不会覆盖函数中包含的键值，这实际上提供了 **1:N** 映射的可能性。
        """

        consumer_dict = {}

        for runnable, binding_map in self.providers + self.dynamic_providers:
            vars = runnable.provider_dict
            for k, v in vars.items():
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
                    if v.__code__.co_argcount == 0:
                        consumer_dict[k] = v()
                    else:
                        consumer_dict[k] = v(vars)
                elif v is None:
                    # 实现规则 4
                    consumer_dict[k] = None

        return {k:v for k,v in consumer_dict.items() if v is not None}

    @property
    def provider_tree(self):
        """
        从当前 runnable 开始，获取所有上游绑定的 provider 及其祖先。
        """
        tree = {"consumer": self, "provider_tree": []}
        for provider, binding_map in self.providers:
            tree["provider_tree"].append({
                "provider": provider,
                "binding_map": binding_map,
                "provider_tree": provider.provider_tree
            })
        return tree
    
    @property
    def consumer_tree(self):
        """
        从当前 runnable 开始，获取所有下游绑定的 consumer 及其子孙。
        """
        tree = {"provider": self, "consumer_tree": []}
        for consumer, binding_map in self.consumers:
            tree["consumer_tree"].append({
                "consumer": consumer,
                "binding_map": binding_map,
                "consumer_tree": consumer.consumer_tree
            })
        return tree

class PassthroughBinding(BindingManager):
    """
    透传字典结构到 provider_dict
    """
    def __init__(self, binding_map: Dict=None):
        super().__init__()
        self.name = f"PassthroughBinding-{id(self)}"
        self.binding_map = binding_map or {}

    @property
    def provider_dict(self):
        return {k: v for k, v in self.binding_map.items() if v is not None}
