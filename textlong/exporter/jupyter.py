from ..utils import raise_not_install
import os

def export_jupyter(input_file: str, output_file: str=None):
    try:
        import jupytext
    except Exception as e:
        raise_not_install("please install jupytext: `pip install jupytext`")

    if input_file:
        if not output_file:
            output_file = input_file + ".ipynb"

        with open(input_file, 'r') as f:
            md_contents = f.read()

        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        if md_contents:
            notebook = jupytext.reads(md_contents, fmt='md')
            jupytext.write(notebook, output_file, fmt='ipynb')
    
    return True
