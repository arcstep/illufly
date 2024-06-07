import copy
from typing import Union, List
from langchain_core.documents import Document
from langchain.globals import set_verbose, get_verbose
from langchain.prompts import PromptTemplate, ChatPromptTemplate, MessagesPlaceholder

from .documents import IntelliDocuments
from .output_parser import MarkdownOutputParser
from ..parser import parse_markdown
from ..hub import load_prompt
from ..utils import markdown

def create_chain(llm, prompt_template, **kwargs):
    if not llm:
        raise ValueError("LLM can't be None !")
    prompt = prompt_template.partial(**kwargs)
    return prompt | llm

def call_markdown_chain(chain, input):
    if get_verbose():
        print("\033[34m" + "#"*20, "PROMPT BEGIN", "#"*20)  # 蓝色
        print(chain.get_prompts()[0].format(**input))
        print("#"*20, "PROMPT END ", "#"*20 + "\033[0m")  # 重置颜色

    text = ""
    for chunk in chain.stream(input):
        text += chunk.content
        print(chunk.content, end="")

    print("\033[32m" + f"\n\n实际字数: {len(text)}" + "\033[0m")  # 绿色
    return MarkdownOutputParser().invoke(text)[0]

class Writing():
    """
    写作。
    """

    def __init__(
        self,
        todo_docs: Union[str, IntelliDocuments]=None,
        ref_docs: Union[str, IntelliDocuments]=None,
        llm=None,
        **kwargs
    ):

        self.llm = llm

        self.knowledge = {}
        self.save_path = ""

        if isinstance(ref_docs, str) or ref_docs == None:
            self.ref_docs = IntelliDocuments(doc_str=ref_docs)
        elif isinstance(ref_docs, IntelliDocuments):
            self.ref_docs = docs
        else:
            raise ValueError("ref_docs MUST be str or IntelliDocuments")

        if isinstance(todo_docs, str) or todo_docs == None:
            self.todo_docs = IntelliDocuments(doc_str=todo_docs)
        elif isinstance(todo_docs, IntelliDocuments):
            self.todo_docs = todo_docs
        else:
            raise ValueError("todo_docs MUST be str or IntelliDocuments")

    @property
    def documents(self):
        return self.todo_docs.documents

    @property
    def markdown(self):
        return self.todo_docs.markdown

    def clone(self, new_document_id: str=None):
        """
        返回一个新的对象，并确保所有对象都已经深度拷贝。
        
        如果不指定 new_document_id 就仅克隆到内存。
        TODO:
        """
        pass

    def save_as_ref(self):
        """
        将 todo_docs 保存为 ref_docs
        
        常用于先创作提纲，再进行扩写的场景。
        """
        self.ref_docs = copy.deepcopy(self.todo_docs)
        return self.ref_docs.documents

    def save(self):
        """
        保存
        TODO: 支持按用户
        TODO: 序列化到文件
        TODO: 序列化到数据库
        """
        pass

    def load(self, document_id: str=None):
        """
        加载
        TODO: 支持按用户
        TODO: 从文件反序列化
        TODO: 从数据库反序列化
        """
        pass

    def load_prompts(self):
        """
        加载提示语模板
        TODO: 支持按用户加载默认提示语模板
        TODO: 初始化时将默认提示语模板路径修改为用户指定的模板
        """
        pass

    def idea(self, task: str, template_id: str=None):
        """
        创意
        
        - 当存在ref_docs时，将其作为创意参考。
        - TODO: 根据任务要求推理，选择不同模板
        """
        prompt = load_prompt(template_id or "IDEA")
        doc = f'你已经完成的创作如下：\n{self.ref_docs.markdown}' if self.ref_docs != None else ''
        chain = create_chain(self.llm, prompt, todo_doc=doc)
        resp_md = call_markdown_chain(chain, {"task": task})
        self.todo_docs.import_markdown(resp_md)

        return self.todo_docs
    
    def outline(self, task: str, template_id: str=None):
        """
        提纲
        """
        return self.idea(task, template_id or "OUTLINE")

    def outline_self(self, task: str=None, template_id: str=None):
        """
        提纲
        
        - 当存在ref_docs时，针对扩写要求放大提纲。
        - TODO: 当指定局部修改时
        - TODO: 根据任务要求推理，选择不同模板
        """
        if not self.ref_docs.documents:
            raise ValueError("必须提供`ref_docs`作为扩写依据")

        return self.detail(task, template_id or "OUTLINE_SELF")

    def detail(self, task: str=None, template_id: str=None):
        """
        扩写
        
        - 必须提供《参考提纲》作为扩写依据。
        - TODO: 当指定局部修改时
        - TODO: 根据任务要求推理，选择不同模板
        """
        if not self.ref_docs.documents:
            raise ValueError("必须提供`ref_docs`作为扩写依据")

        self.todo_docs = copy.deepcopy(self.ref_docs)
        prompt = load_prompt(template_id or "OUTLINE_DETAIL")

        for doc in self.todo_docs.get_outline_task():
            prev_doc = markdown(self.todo_docs.get_prev_documents(doc))
            next_doc = markdown(self.todo_docs.get_next_documents(doc))
            chain = create_chain(
                self.llm,
                prompt,
                prev_doc=prev_doc,
                next_doc=next_doc,
                todo_doc=f'>->>>\n{doc.page_content}\n<-<<<'
            )

            task_howto = f"{task or ''}\n请仅针对上述`>->>>`和`<-<<<`包围的部份扩写。"
            resp_md = call_markdown_chain(chain, {"task": task_howto})
            reply_docs = parse_markdown(resp_md)
            self.todo_docs.replace_documents(index_doc=doc, docs=reply_docs)

        return self.todo_docs

    def fetch(self, task: str=None, template_id: str=None):
        """
        提取

        - 按任务意图提取文档
        - 默认提取`摘要`，可以通过`task`指定知识三元组、人物、工作流程等具体要求
        - TODO: 根据任务要求推理，选择不同模板
        """
        if not self.ref_docs.documents:
            raise ValueError("必须提供`ref_docs`作为提取目标")

        prompt = load_prompt(template_id or "SUMMARISE")
        chain = create_chain(self.llm, prompt, todo_doc=self.ref_docs.markdown)
        resp_md = call_markdown_chain(chain, {"task": task})
        self.todo_docs.import_markdown(resp_md)

        return self.todo_docs
        
    def translate(self, task: str=None, from_lang: str="中文", to_lang: str="英文", template_id: str=None, k: int=1000):
        """
        翻译
        """
        refine_task = f'请帮我翻译，从{from_lang}到{to_lang}。{task or ""}'
        return self.refine(refine_task, template_id or "TRANSLATE", k)

    def refine(self, task: str, template_id: str=None, k: int=1000):
        """
        修改

        - 按修改意图和滚动上下文窗口修改长文档，例如替换文中的产品名称
        - TODO: 当指定局部修改时
        """
        if not self.ref_docs.documents:
            raise ValueError("必须提供`ref_docs`作为修改目标")

        prompt = load_prompt(template_id or "REFINE")

        resp_md = ""
        task_docs = []
        md_len = 0
        
        def create_md(docs):
            md = markdown(docs)
            if len(md):
                todo_doc = f'>->>>\n{md}\n<-<<<'
                prev_doc = markdown(self.ref_docs.get_prev_documents(docs[0]))
                chain = create_chain(self.llm, prompt, prev_doc=prev_doc, todo_doc=todo_doc)
                task_howto = f"{task or ''}\n请针对`>->>>`和`<-<<<`包围的部份重写。"
                return call_markdown_chain(chain, {"task": task_howto})
            else:
                return ""

        for doc in self.ref_docs.documents:
            md_len += len(doc.page_content)
            task_docs.append(doc)
            if md_len <= k:
                continue

            resp_md += create_md(task_docs) + "\n\n"
            md_len = 0
            task_docs = []

        if task_docs:
            resp_md += create_md(task_docs)

        self.todo_docs.import_markdown(resp_md)
        return self.todo_docs

    def embedding(self):
        """
        向量编码

        - TODO: 对todo_docs做向量编码，并保存到向量数据库
        - TODO: 按 Document 缓存编码结果
        """
        pass

    def search(self):
        """
        相似性查询

        - TODO: 对文档列表做向量相似性查询
        - TODO: 将本地文档文件资料作为向量相似性查询依据
        - TODO: 将查询结果作为创作依据(knowledge变量)
        """
        pass

    def chat(self):
        """
        对话

        - TODO: RAG对话
        """
        pass

