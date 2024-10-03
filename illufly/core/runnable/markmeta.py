import os
import fnmatch
import time
import random
from typing import Union, List
from ..runnable import Runnable
from ..document import Document
from ...io import EventBlock
from ...config import get_env
from ...utils import minify_text, count_tokens


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
    
    def call(self, *args, **kwargs):
        pass

    def save(self) -> List[Document]:
        """
        将文档保存为 MarkMeta 文件。
        """
        source_files = {}
        for doc in self.documents:
            k = doc.metadata['source']
            if source_files[k] is None:
                source_files[k] = []
            source_files[k].append(doc)
        for source, docs in source_files.items():
            path = os.path.join(get_env("ILLUFLY_DOCS"), source)
            with open(path, 'w', encoding='utf-8') as f:
                for doc in docs:
                    metadata_line = "@metadata"
                    for k, v in doc.metadata.items():
                        metadata_line += f" {k}={json.dumps(v, ensure_ascii=False)}"
                    f.write(metadata_line)
                    f.write(doc.text)
                    f.write("\n")
                yield(EventBlock("info", f"已成功保存文件 {source} ，其中包含 {len(docs)} 个片段。"))

    def load_text(self, text: str, source: str=None) -> List[Document]:
        """
        将文本内容加载为 MarkMeta 文档。
        """
        docs = self.split_with_metadata(text)
        for doc in docs:
            if source:
                doc.metadata['source'] = source
            else:
                if 'id' in docs[0].metadata:
                    doc.metadata['source'] = f"{docs[0].metadata['id']}.md"
            if count_tokens(doc.text) > self.chunk_size:
                chunks = self.split_text_recursive(doc.text, doc.metadata['source'])
                self.documents.extend(chunks)
            else:
                self.documents.append(doc)
        return self.documents

    def _load_file(self, file_path: str) -> List[Document]:
        """
        加载单个文件。
        """
        if not file_path or not os.path.exists(file_path):
            yield(EventBlock("warn", f"文件不存在 {file_path}"))
        with open(file_path, 'r', encoding='utf-8') as f:
            txt = f.read()
            if str(txt).strip() == "":
                yield(EventBlock("warn", f"文件内容为空 {file_path}"))
                return
            self.load_text(txt)
            yield(EventBlock("info", f"已成功加载文件 {file_path} ，其中包含 {len(self.documents)} 个片段。"))

    def split_with_metadata(self, text: str) -> List[Document]:
        """
        按照 @metadata 标签切分文档，每个片段单元作为独立的 Document 元素，并提取元数据。
        """
        documents = []
        split_text = text.split("\n@metadata")
        for segment in split_text:
            lines = segment.split("\n")
            metadata_line = lines[0].strip()
            content = "\n".join(lines[1:]).strip()

            metadata = {}
            metadata_items = metadata_line.split(",")
            for item in metadata_items:
                if "=" in item:
                    k, v = item.split("=", 1)
                    metadata[k.strip()] = v.strip()

            doc = Document(text=content, metadata=metadata)
            documents.append(doc)
        return documents

    def load(self, *files, **kwargs):
        """
        将文件作为 markdown 文本导入。
        """
        self.documents.clear()

        files = list(files) or self.get_files(self.directory, self.filename_filter, self.extensions)
        for file_path in files:
            try:
                self._load_file(file_path)
            except Exception as e:
                yield(EventBlock("warn", f"读取文件失败 {file_path}: {e}"))

    def get_files(self, directory, filename_filter, extensions):
        """
        获取目录下所有符合条件的文件。
        """
        matches = []
        path = os.path.join(get_env("ILLUFLY_DOCS"), directory)
        for root, dirnames, filenames in os.walk(path):
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]  # 排除隐藏文件夹
            filenames = [f for f in filenames if not f.startswith('.')]  # 排除隐藏文件
            for extension in extensions:
                for filename in fnmatch.filter(filenames, filename_filter + extension):
                    matches.append(os.path.join(root, filename))
        return matches

    def split_text_recursive(self, text: str, source: str) -> List[Document]:
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
