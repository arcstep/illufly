import os
import fnmatch
from typing import Union, List
from ..types import Markdown, Document, TextBlock
from ..core.runnable import Importer
from ..config import get_env
from ..utils import minify_text, count_tokens

class MarkdownFileImporter(Importer):
    def __init__(self, dir: str=None, filter: str=None, exts: list = None, chunk_size: int=None, chunk_overlap: int=None, **kwargs):
        """
        初始化 Markdown 文件导入器。

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

    def call(self, **kwargs) -> Markdown:
        """
        将文件作为 markdown 文本导入。
        """
        self.documents.clear()

        files = self.get_files(self.directory, self.filename_filter, self.extensions)
        for file in files:
            abs_file = os.path.abspath(file)
            try:
                if not os.path.exists(abs_file):
                    yield(TextBlock("warn", f"文件不存在 {abs_file}"))
                    continue

                with open(abs_file, 'r', encoding='utf-8') as f:
                    txt = f.read()
                    if str(txt).strip() == "":
                        yield(TextBlock("warn", f"文件内容为空 {file}"))
                        continue
                    docs = self.split_markdown(txt, file)
                    self.documents.extend(docs)
            except Exception as e:
                yield(TextBlock("warn", f"读取文件失败 {abs_file}: {e}"))

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
