from typing import Union
import pandas as pd

class Dataset:
    def __init__(self, df: Union[pd.DataFrame]=None, desc: str=None):
        self.df = df
        self.desc = desc
