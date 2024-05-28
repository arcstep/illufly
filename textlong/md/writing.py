from .documents import IntelliDocuments
from .tools import create_outline_chain, create_detail_chain

def call_chain(chain, input):
    text = ""
    for chunk in chain.stream(input):
        text += chunk.content
        print(chunk.content, end="")
    
    print(f"\n\n实际字数: {len(text)}")
    return text

class Writing():
    def __init__(self, outline=None, detail=None, llm=None):
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
        self.target_outline.documents = call_chain(chain, {"task": task})
        self.target_outline.build_index("1")
        return self.target_outline.documents

    def detail(self, task: str):
        """
        根据提纲扩写细节。
        """
        chain = create_detail_chain(self.llm)
        self.target_detail.documents = call_chain(chain, {"task": task})
        self.target_detail.build_index("1")
        return self.target_detail.documents

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