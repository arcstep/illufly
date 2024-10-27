import os
import fnmatch
import json
import re
from typing import Union, List
from ..runnable import Runnable
from ..document import Document
from ...io import EventBlock
from ...config import get_env
from ...utils import minify_text, count_tokens, raise_invalid_params, filter_kwargs
import numpy as np

class MarkMeta(Runnable):
    """
    MarkMeta 持久化时为基于 Markdown 语法的纯文本，但增加了一些扩展标签；
    加载到内存时主要属性为 Document 列表，并将标签转化为 Document 元素的 meta 键值数据。

    MarkMeta 文件中的标签语法：
    - 扩展标签都独占一行，且以 @ 开头，行首不允许多余空格
    - 主要标签包括 @meta @index @end
    - @meta 包含键值描述语法：<!-- @meta {"k1":v1, "k2":v2, …} -->
    - MarkMeta 文档被 @meta 标签分割成多个片段，从开头或 @meta 标签的下一行开始，到下一个 @meta 标签前一行结束
    - 其他标签智能包含在 @meta 标签中

    MarkMeta 导入和导出：
    - 处理导入
        - 按 @meta 标签切分文档，每个片段单元作为独立的 Document 元素
        - 如果单个文档内容超过 chunk_size 限制，则滚动切分，并增补 ID 作为新的 Document 元素
        - 优先使用 @meta 所在行的键值描述来初始化 Document 的 meta 数据
        - 片段单元的内容都作为 Document 的 text 属性
    - @TODO: 处理 @index 标签
        - Document 的 index 属性是一个列表，额外存储了专门指定的文本嵌入内容，建立索引时应当替代 text 内容
        - 可以在文档中使用 @index 指定开始位置，遇到@end结束
        - @index 支持多段落
    - 处理导出时
        - 将 Document 的 text 属性作为文本内容，meta 作为元数据
        - 由于 text 属性中仍然包含可能存在的 @index 标签，所以导出时不必专门保存 index 内容

    在向量模型、向量数据库中使用 MarkMeta 文件:
    - 导入时按照 Document 元素作为切分单元

    导出时，由对话模型将输出结果保存为 MarkMeta 文件。
    """
    @classmethod
    def allowed_params(cls):
        return {
            "dir": "从这个目录路径导入文件，默认为 ILLUFLY_DOCS 环境变量",
            "filter": "文件名过滤器，可以直接写文件名，或者使用 * 号等通配符",
            "exts": "文件扩展名列表，默认支持 md, Md, MD, markdown, MARKDOWN 等",
            "chunk_size": "每个块的大小，这可能是各个模型处理中对 token 限制要求的，默认 1024",
            "chunk_overlap": "每个块的覆盖大小，默认 100",
            **Runnable.allowed_params()
        }

    def __init__(self, dir: str=None, filter: str=None, exts: list = None, chunk_size: int=None, chunk_overlap: int=None, **kwargs):
        raise_invalid_params(kwargs, self.__class__.allowed_params())

        super().__init__(**kwargs)
        self.directory = dir or get_env("ILLUFLY_DOCS")
        self.filename_filter = filter or '*'
        self.extensions = exts or ['*.md', '*.Md', '*.MD', '*.markdown', '*.MARKDOWN']
        self.chunk_size = chunk_size or 1024
        self.chunk_overlap = chunk_overlap or 100
        self.documents = []

    def clear(self):
        self.documents.clear()

    @property
    def last_output(self):
        return self.documents
    
    def save(self) -> List[Document]:
        """
        将文档保存为 MarkMeta 文件。
        """
        source_files = {}
        for doc in self.documents:
            k = doc.meta['source']
            if source_files.get(k) is None:
                source_files[k] = []
            source_files[k].append(doc)
        for source, docs in source_files.items():
            path = os.path.join(get_env("ILLUFLY_DOCS"), source)
            if not os.path.exists(path):
                os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                for doc in docs:
                    # 将 meta 字典转换为 JSON 字符串
                    # 删除 embeddings 键值对，以避免保存向量数据
                    doc.meta.pop('embeddings', None)
                    meta_line = f"@meta {json.dumps(doc.meta, ensure_ascii=False)}"
                    f.write("\n<!-- " + meta_line + " -->\n")
                    f.write(doc.text + "\n")
                yield EventBlock("info", f"Saved file {source} with {len(docs)} chunks")

    def call(self, *files, **kwargs):
        yield from self.load(*files, **kwargs)

    def load(self, **kwargs):
        """
        load 方法是加载文档时最常用的方法。
        """
        self.documents.clear()

        files = self.get_files(self.directory, self.filename_filter, self.extensions)
        for file_path in files:
            try:
                yield from self.load_file(file_path)
            except Exception as e:
                yield(EventBlock("warn", f"读取文件失败 {file_path}: {e}"))

    def get_files(self, path, filename_filter, extensions):
        """
        获取目录下所有符合条件的文件。
        """
        matches = []
        for root, dirnames, filenames in os.walk(path):
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]  # 排除隐藏文件夹
            filenames = [f for f in filenames if not f.startswith('.')]  # 排除隐藏文件
            for extension in extensions:
                for filename in fnmatch.filter(filenames, filename_filter + extension):
                    matches.append(os.path.join(root, filename))
        return matches

    def load_file(self, abs_path: str) -> List[Document]:
        """
        加载单个文件。
        """
        if not abs_path or not os.path.exists(abs_path):
            yield(EventBlock("warn", f"文件不存在 {abs_path}"))

        with open(abs_path, 'r', encoding='utf-8') as f:
            txt = f.read()
            if str(txt).strip() == "":
                yield(EventBlock("warn", f"文件内容为空 {abs_path}"))
                return
            self.load_text(txt, source=abs_path)
            yield(EventBlock("info", f"已成功加载文件 {abs_path} ，其中包含 {len(self.documents)} 个片段。"))

    def load_text(self, text: str, source: str=None) -> List[Document]:
        """
        将文本内容加载为 MarkMeta 文档。
        """
        docs = self.split_with_meta(text)
        for doc in docs:
            if doc.meta.get('source') is None:
                new_source = source or f"{docs[0].meta.get('id', 'unknown')}.md"
                doc.meta["source"] = new_source

            if count_tokens(doc.text) > self.chunk_size:
                chunks = self.split_text_recursive(doc.text, doc.meta['source'])
                self.documents.extend(chunks)
            else:
                self.documents.append(doc)
        return self.documents

    def split_with_meta(self, text: str) -> List[Document]:
        """
        按照 @meta 标签切分文档，每个片段单元作为独立的 Document 元素，并提取元数据。
        """
        documents = []
        split_text = re.split(r'\s*<!--\s*@meta', "\n" + text)
        for segment in split_text:
            if segment.strip() == "":
                continue
            lines = segment.split("\n")
            meta_line = lines[0].strip().replace("<!--", "").replace("-->", "").strip()
            content = "\n".join(lines[1:]).strip()

            try:
                # 直接将 meta_line 作为 JSON 解析
                meta = json.loads(meta_line)
            except json.JSONDecodeError as e:
                meta = {"raw_meta": meta_line}

            doc = Document(text=content, meta=meta)
            documents.append(doc)
        return documents

    def split_text_recursive(self, text: str, source: str) -> List[Document]:
        """
        按照指定规则分割Markdown文档。

        :return: 分割后Document对象列表
        """
        def split_text(text: str) -> List[str]:
            return text.split('\n')

        def create_chunk(lines: List[str], chunk_index: int) -> Document:
            return Document(text='\n'.join(lines), meta={"source": f"{source}#{chunk_index}"})

        chunks = []

        if not isinstance(text, str):
            raise ValueError("split_markdown的参数 text 必须是字符串")

        if not text or text.strip() == "":
            return chunks

        lines = split_text(text)
        current_chunk = []
        current_length = 0

        chunk_index = 0
        for line in lines:
            line_length = count_tokens(line)
            if line_length > self.chunk_size:
                continue  # 忽略超过chunk_size的最小单位

            if current_length + line_length > self.chunk_size:
                docs = [d for (l, d) in current_chunk]
                chunks.append(create_chunk(docs, chunk_index))
                
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
            chunks.append(create_chunk(docs, chunk_index))

        return chunks
