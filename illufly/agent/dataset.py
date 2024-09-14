import pandas as pd
from typing import Union

class Dataset:
    def __init__(self, df: Union[pd.DataFrame] = None, desc: str = None):
        self.df = df
        self.desc = desc
    
    def __str__(self):
        return self.desc

    def __repr__(self):
        return f"Dataset(desc={self.desc})"
