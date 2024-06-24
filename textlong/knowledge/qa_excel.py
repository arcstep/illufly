from typing import Iterator, List, Union
from langchain_core.documents import Document
from langchain_community.document_loaders.base import BaseLoader
from ..config import get_folder_root, get_folder_qa
from .base import LocalFilesLoader

import os
import pandas as pd

class QAExcelsLoader(LocalFilesLoader):
    """
    从本地文件中检索Excel文件，并以QA结构返回 Document 对象。
    """

    extensions: List[str] = ["xlsx"]

    def __init__(
        self,
        project_folder: str=None,
        **kwargs
    ):
        kwargs['project_folder'] = project_folder or get_folder_qa()
        super().__init__(**kwargs)

    def detect_df(self, filename: str) -> tuple:
        """
        检测包含QA标记的数据框
        
        规则：
        - 文件名称中包含QA的sheet
        - 以数据框的形式保存整个QA文本
        - 表头应当包含QA列，即至少一列以Q开头，至少一列以A开头，例如： Q-问题 | A-回答
        - 允许表头的上方有其他行，用于说明、总结或作为空行
        """
        result = []

        with pd.ExcelFile(filename) as xls:
            sheet_names = xls.sheet_names

        target_sheets = [name for name in sheet_names if "qa" in name.lower()]

        for sheet_name in target_sheets:
            df = pd.read_excel(filename, sheet_name=sheet_name, header=None, nrows=10)

            for i in range(10):
                # 找到列名称以"q"或"Q"开头且包含"A"或"a"的列
                q_columns = [col for col in df.iloc[i] if str(col)[0].lower() == "q"]
                a_columns = [col for col in df.iloc[i] if str(col)[0].lower() == "a"]

                if q_columns and a_columns:
                    result.append((filename, sheet_name, i, q_columns, a_columns))
                    break

        return result

    def load_docs(self, filename: str, file_loader=None) -> List[Document]:
        """
        Load documents from the specified Excel file.
        """
        dfs = self.detect_df(filename)
        documents = []

        for file_name, sheet_name, start_row, q_columns, a_columns in dfs:
            
            df = pd.read_excel(file_name, sheet_name=sheet_name, header=start_row)

            df_q = df[q_columns].copy()
            df_a = df[a_columns].copy()

            df_q.loc[:, 'Q'] = df_q.apply(lambda row: '\n'.join(row.values.astype(str)), axis=1)
            df_a.loc[:, 'A'] = df_a.apply(lambda row: '\n'.join(row.values.astype(str)), axis=1)

            df_final = pd.concat([df_q['Q'], df_a['A']], axis=1)

            for _, row in df_final.iterrows():
                doc = Document(
                    page_content=row["Q"],
                    metadata={
                        "answer": row["A"],
                        "source": file_name,
                        "sheet": sheet_name,
                    }
                )
                documents.append(doc)

        return documents
