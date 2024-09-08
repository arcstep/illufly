def load_docs(filename: str) -> List[Document]:
    """
    按照文档类型加载文档，并直输出循环拆分后的文档块。
    """
    file_loader = FileLoadFactory.get_loader(filename)
    if file_loader:
        return file_loader.load_and_split(self.text_spliter)
    else:
        return []