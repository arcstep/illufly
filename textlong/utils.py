from typing import List, Union
from langchain_core.documents import Document

def raise_not_install(packages):
    print(f"please install package: '{packages}' with pip or poetry")
    # auto install package
    # subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])

def raise_not_supply_all(info: str, *args):
    if all(arg is None for arg in args):
        raise ValueError(info)

def markdown(docs: List[Document], sep: str=""):
    return sep.join([d.page_content for d in docs])
