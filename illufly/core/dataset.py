from typing import Any, Dict
import pandas as pd
import textwrap

class Dataset:
    """
    数据集。

    默认仅支持 pandas.DataFrame 类型的数据集。可以通过子类继承支持其他类型的数据集。
    """
    def __init__(self, df: pd.DataFrame, name: str, desc: str=None):
        if not desc:
            desc = ""

        if not isinstance(df, pd.DataFrame):
            raise ValueError(f"df 必须是 pandas.DataFrame 类型")
        if desc and not isinstance(desc, str):
            raise ValueError(f"desc 必须是 str 类型")

        self.name = name
        self.df = df
        self.desc = desc or f"关于`{self.name}`的数据集"

    def __repr__(self):
        return f"Dataset(name={self.name}, df={self.df}, desc={self.desc})"

    @property
    def summary(self):
        from .runnable.prompt_template import PromptTemplate

        head = self.df.head()
        example_md = head.to_markdown(index=False)
        summary = PromptTemplate(
            "CODE/DATASET_SUMMARY",
            binding_map={
                "name": lambda: self.name,
                "desc": lambda: self.desc,
                "example_md": lambda: example_md,
            }).format()
        return summary
