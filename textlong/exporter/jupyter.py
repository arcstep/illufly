from ..utils import raise_not_install

def export_jupyter(input_file: str, output_file: str):
    try:
        import jupytext
    except Exception as e:
        raise_not_install("please install jupytext: `pip install jupytext`")

    with open(input_file, 'r') as md_file:
        md_contents = md_file.read()

    notebook = jupytext.reads(md_contents, fmt='md')
    jupytext.write(notebook, output_file, fmt='ipynb')