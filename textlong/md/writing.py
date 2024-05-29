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
        return self.target_outline.import_markdown(text)

    def detail(self, task: str):
        """
        根据提纲扩写细节。
        """
        chain = create_detail_chain(self.llm)
        text = call_markdown_chain(chain, {"task": task})
        return self.target_detail.import_markdown(text)

    def fetch(self):
        """
        从文字中提取大纲。
        """
        chain = create_detail_chain(self.llm)

    def refine(self):
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