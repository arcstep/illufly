from typing import Union, List
from .documents import IntelliDocuments
from .tools import create_outline_chain, create_detail_chain
from .output_parser import MarkdownOutputParser
from abc import ABC, abstractclassmethod
import copy

def call_markdown_chain(chain, input):
    text = ""
    for chunk in chain.stream(input):
        text += chunk.content
        print(chunk.content, end="")

    print(f"\n\n实际字数: {len(text)}")
    return MarkdownOutputParser().invoke(text)[0]

class BaseWriting(ABC):
    """
    写作任务。
    - outline 构思大纲
    - detail  扩写细节
    - fetch   提取大纲
    - refine_outline 优化大纲
    - refine 优化改写
    - rewrite 重写
    - translate 翻译
    """

    def __init__(self, document: Union[str, IntelliDocuments]=None, llm=None, **kwargs):
        self.llm = llm
        self.chain = create_outline_chain(self.llm)
        
        if isinstance(document, str):
            self.todo_docs = IntelliDocuments(doc_str=document)
        elif isinstance(document, IntelliDocuments):
            self.todo_docs = document
        else:
            self.todo_docs = IntelliDocuments()
    
    @abstractclassmethod
    def write(self, task: str):
        """写作任务"""
        pass

    @property
    def documents(self):
        return self.todo_docs.documents

    @property
    def markdown(self):
        return IntelliDocuments.get_markdown(self.documents)

    def fetch_outline(self):
        """
        从文字中提取大纲。
        """
        chain = create_detail_chain(self.llm)

    def refine_detail(self):
        """
        优化文字内容。
        """
        chain = create_detail_chain(self.llm)

    def refine_outline(self):
        """
        优化写作提纲。
        """
        chain = create_detail_chain(self.llm)
    
    def rewrite(self):
        """
        根据已有文字内容仿写。
        """
        chain = create_detail_chain(self.llm)

    def translate(self):
        """
        根据已有文字内容翻译。
        """
        chain = create_detail_chain(self.llm)    

class Writing(BaseWriting):
    """创作提纲"""

    def write(self, task: str):
        text = call_markdown_chain(self.chain, {"task": task})
        self.todo_docs.import_markdown(text)
        return self.todo_docs
    
class Outlining(BaseWriting):
    """扩写"""

    def __init__(self, outline: Union[str, IntelliDocuments, BaseWriting], detail=True, **kwargs):
        if isinstance(outline, str):
            self.outline_docs = IntelliDocuments(doc_str=outline)
        elif isinstance(outline, BaseWriting):
            self.outline_docs = copy.deepcopy(outline.todo_docs)
            if 'llm' not in kwargs:
                kwargs['llm'] = outline.llm
        elif isinstance(outline, IntelliDocuments):
            self.outline_docs = outline
        else:
            self.outline_docs = IntelliDocuments()

        super().__init__(**kwargs)
        
        # 如果detail为False，就使用默认的大纲扩展
        if detail:
            self.chain = create_detail_chain(self.llm)

    def write(self, task: str=None):
        if not self.outline_docs.documents:
            raise ValueError("MUST supply outline for Outlining")
        
        task_nodes = self.outline_docs.get_leaf_outline()
        self.todo_docs.documents = copy.deepcopy(self.outline_docs.documents)

        # 批量扩写任务
        for node in task_nodes:
            task_title = node.page_content
            task_docs = self.outline_docs.get_documents(task_title)
            task = f"请根据提纲要求完成续写，标题和要求为：\n{IntelliDocuments.get_markdown(task_docs)}"
            outline_relv_docs = self.outline_docs.get_relevant_documents(task_title)
            detail_prev_docs = self.todo_docs.get_prev_documents(task_title)
            print("#"*20, "PROMPT BEGIN", "#"*20)
            print(self.chain.get_prompts()[0].format(
                task=task,
                outline=IntelliDocuments.get_markdown(outline_relv_docs),
                detail=IntelliDocuments.get_markdown(detail_prev_docs),
            ))
            print("#"*20, "PROMPT  END ", "#"*20)
            resp_md = call_markdown_chain(
                self.chain,
                {
                    "task": task,
                    "outline": IntelliDocuments.get_markdown(outline_relv_docs),
                    "detail": IntelliDocuments.get_markdown(detail_prev_docs),
                }
            )
            reply_md = IntelliDocuments.parse_markdown(resp_md)
            self.todo_docs.replace_documents(new_docs=reply_md, title=task_title)

        return self.todo_docs.documents
