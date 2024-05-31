from .documents import IntelliDocuments
from .tools import create_outline_chain, create_detail_chain
from .output_parser import MarkdownOutputParser

def call_markdown_chain(chain, input):
    text = ""
    for chunk in chain.stream(input):
        text += chunk.content
        print(chunk.content, end="")

    print(f"\n\n实际字数: {len(text)}")
    return MarkdownOutputParser().invoke(text)[0]

class Writing():
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

    def __init__(self, outline=None, detail=None, llm=None):
        self.llm = llm
        # 源文档，适合仿写、改写、翻译等功能
        self.source_outline = IntelliDocuments(doc_str=outline, llm=llm)
        self.source_detail = IntelliDocuments(doc_str=outline, llm=llm)
        # 目标文档
        self.target_outline = IntelliDocuments(llm=llm)
        self.target_detail = IntelliDocuments(llm=llm)

    def outline(self, task: str):
        """
        从零开始创建写作大纲。
        """
        chain = create_outline_chain(self.llm)
        text = call_markdown_chain(chain, {"task": task})
        self.target_outline.import_markdown(text)
        return self.target_outline.documents

    def detail(self):
        """
        根据提纲扩写细节。
        """
        chain = create_detail_chain(self.llm)

        task_nodes = self.target_outline.get_leaf_outline()
        self.target_detail.documents = self.target_outline.documents

        # 批量扩写任务
        for node in task_nodes:
            task_title = node.page_content
            task_docs = self.target_outline.get_documents(task_title)
            task = f"请根据提纲要求完成续写，标题和要求为：\n{IntelliDocuments.get_markdown(task_docs)}"
            outline_docs = self.target_outline.get_relevant_documents(task_title)
            detail_prev_docs = self.target_detail.get_prev_documents(task_title)
            print("#"*20, "PROMPT BEGIN", "#"*20)
            print(chain.get_prompts()[0].format(
                task=task,
                outline=IntelliDocuments.get_markdown(outline_docs),
                detail=IntelliDocuments.get_markdown(detail_prev_docs),
            ))
            print("#"*20, "PROMPT  END ", "#"*20)
            resp_md = call_markdown_chain(
                chain,
                {
                    "task": task,
                    "outline": IntelliDocuments.get_markdown(outline_docs),
                    "detail": IntelliDocuments.get_markdown(detail_prev_docs),
                }
            )
            resp_docs = IntelliDocuments.parse_markdown(resp_md)
            self.target_detail.replace_documents(new_docs=resp_docs, title=task_title)

        return self.target_detail.documents

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