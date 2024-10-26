from typing import Any, Dict
import pandas as pd
import textwrap

class Dataset:
    """
    数据集。

    默认仅支持 pandas.DataFrame 类型的数据集。可以通过子类继承支持其他类型的数据集。
    """
    def __init__(self, datasets: Dict[str, Any]):
        for ds_name, ds in datasets.items():
            if not isinstance(ds, dict):
                raise ValueError(f"数据集 {ds_name} 必须是 dict 类型: {{'df': pandas.DataFrame, 'desc': str}}")
            if "df" not in ds or not isinstance(ds["df"], pd.DataFrame):
                raise ValueError(f"数据集 {ds_name} 必须有一个 'df' 键，其值是 pandas.DataFrame 类型")
            if ds["df"].empty:
                raise ValueError(f"数据集 {ds_name} 的 'df' 键不能是空的 DataFrame")
            if not ds.get("desc") or not isinstance(ds["desc"], str):
                raise ValueError(f"数据集 {ds_name} 必须有一个 'desc' 键，其值是 str 类型")

        self.datasets = datasets

    def __repr__(self):
        return f"Dataset(datasets={self.datasets})"

    @property
    def names(self):
        return ', '.join(list(self.datasets.keys()))
    
    @property
    def df(self):
        return {name: ds["df"] for name, ds in self.datasets.items()}

    @property
    def description(self):
        return '\n - '.join([ds["desc"] for ds in self.datasets.values()])

    @property
    def summary(self):
        datasets = []
        if self.datasets:
            for ds_name, dataset in self.datasets.items():
                head = dataset["df"].head()
                example_md = head.to_markdown(index=False)
                datasets.append(textwrap.dedent(f"""
                ------------------------------
                **数据集名称：**
                {ds_name}

                **部份数据样例：**

                """) + example_md)

        return '\n'.join(datasets)
