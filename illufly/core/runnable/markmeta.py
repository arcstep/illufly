import os
import fnmatch
from typing import Union, List
from ..types import Markdown, Document, EventBlock
from ..core.runnable import Importer
from ..config import get_env
from ..utils import minify_text, count_tokens

class MarkMeta(Runnable):
    """
    MarkMeta 持久化时为基于 Markdown 语法的纯文本，但增加了一些扩展标签；
    加载到内存时主要属性为 Document 列表，并将标签转化为 Document 元素的 metadata 键值数据。

    MarkMeta 文件中的标签语法：
    - 扩展标签都独占一行，且以 @ 开头，行首不允许多余空格
    - 主要标签包括 @metadata @index @end
    - @metadata 包含键值描述语法：@metadata k1=v1, k2=v2, …
    - MarkMeta 文档被 @metadata 标签分割成多个片段，从开头或 @metadata 标签的下一行开始，到下一个 @metadata 标签前一行结束
    - 其他标签智能包含在 @metadata 标签中

    MarkMeta 导入和导出：
    - 处理导入
        - 按 @metadata 标签切分文档，每个片段单元作为独立的 Document 元素
        - 如果单个文档内容超过 chunk_size 限制，则滚动切分，并增补 ID 作为新的 Document 元素
        - 优先使用 @metadata 所在行的键值描述来初始化 Document 的 metadata 数据
        - 片段单元的内容都作为 Document 的 text 属性
    - 处理 @index 标签
        - Document 的 index 属性是一个列表，额外存储了专门指定的文本嵌入内容，建立索引时应当替代 text 内容
        - 可以在文档中使用 @index 指定开始位置，遇到@end结束
        - @index 支持多段落
    - 处理导出时
        - 将 Document 的 text 属性作为文本内容，metadata 作为元数据
        - 由于 text 属性中仍然包含可能存在的 @index 标签，所以导出时不必专门保存 index 内容

    在向量模型、向量数据库中使用 MarkMeta 文件:
    - 导入时按照 Document 元素作为切分单元

    导出时，由对话模型将输出结果保存为 MarkMeta 文件。
    """
    def __init__(self, dir: str=None, filter: str=None, exts: list = None, chunk_size: int=None, chunk_overlap: int=None, **kwargs):
        """
        :param dir: 从这个目录路径导入文件
        :param filter: 文件名过滤器，可以直接写文件名，或者使用 * 号等通配符
        :param exts: 文件扩展名列表，默认支持 md, Md, MD, markdown, MARKDOWN 等
        :param chunk_size: 每个块的大小，这可能是各个模型处理中对 token 限制要求的，默认 2048
        :param chunk_overlap: 每个块的覆盖大小，默认 100
        """

        super().__init__(**kwargs)
        self.directory = dir or get_env("ILLUFLY_DOCS")
        self.filename_filter = filter or '*'
        self.extensions = exts or ['*.md', '*.Md', '*.MD', '*.markdown', '*.MARKDOWN']
        self.chunk_size = chunk_size or 2048
        self.chunk_overlap = chunk_overlap or 100
        self.documents = []

    @property
    def last_output(self):
        return self.documents

    def import_files(self, *files, **kwargs) -> Markdown:
        """
        将文件作为 markdown 文本导入。
        """
        self.documents.clear()

        files = list(files) or self.get_files(self.directory, self.filename_filter, self.extensions)
        for file in files:
            abs_file = os.path.abspath(file)
            try:
                if not os.path.exists(abs_file):
                    yield(EventBlock("warn", f"文件不存在 {abs_file}"))
                    continue

                with open(abs_file, 'r', encoding='utf-8') as f:
                    txt = f.read()
                    if str(txt).strip() == "":
                        yield(EventBlock("warn", f"文件内容为空 {file}"))
                        continue
                    docs = self.split_markdown(txt, file)
                    self.documents.extend(docs)
            except Exception as e:
                yield(EventBlock("warn", f"读取文件失败 {abs_file}: {e}"))

    def get_files(self, directory, filename_filter, extensions):
        matches = []
        for root, dirnames, filenames in os.walk(directory):
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]  # 排除隐藏文件夹
            filenames = [f for f in filenames if not f.startswith('.')]  # 排除隐藏文件
            for extension in extensions:
                for filename in fnmatch.filter(filenames, filename_filter + extension):
                    matches.append(os.path.join(root, filename))
        return matches

    def split_markdown(self, text: str, source: str) -> List[Document]:
        """
        按照指定规则分割Markdown文档。

        :return: 分割后Document对象列表
        """
        def split_text(text: str) -> List[str]:
            return text.split('\n')

        def create_chunk(lines: List[str]) -> Document:
            return Document(text='\n'.join(lines), metadata={"source": source})

        chunks = []

        if not isinstance(text, str):
            raise ValueError("split_markdown的参数 text 必须是字符串")

        if not text or text.strip() == "":
            return chunks

        lines = split_text(text)
        current_chunk = []
        current_length = 0

        for line in lines:
            line_length = count_tokens(line)
            if line_length > self.chunk_size:
                continue  # 忽略超过chunk_size的最小单位

            if current_length + line_length > self.chunk_size:
                docs = [d for (l, d) in current_chunk]
                chunks.append(create_chunk(docs))
                
                # 计算重叠部分
                overlap_length = 0
                overlap_chunk = []
                for l, d in reversed(current_chunk):
                    overlap_length += l
                    overlap_chunk.insert(0, d)
                    if overlap_length >= self.chunk_overlap or overlap_length >= self.chunk_size / 2:
                        break

                current_chunk = [(count_tokens(d), d) for d in overlap_chunk]
                current_length = sum(l for l, _ in current_chunk)
                continue

            current_chunk.append((line_length, line))
            current_length += line_length
        if current_chunk:
            docs = [d for l, d in current_chunk]
            chunks.append(create_chunk(docs))

        return chunks
