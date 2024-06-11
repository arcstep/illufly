from ..utils import raise_not_install

def export_jupyter(input_file: str, output_file: str):
    try:
        import jupytext
    except Exception as e:
        raise_not_install("please install jupytext: `pip install jupytext`")

    if input_file and output_file:
        input_file = input_file if input_file.endswith(".md") else input_file + ".md"
        output_file = output_file if output_file.endswith(".ipynb") else output_file + ".ipynb"

        with open(input_file, 'r') as md_file:
            md_contents = md_file.read()

        if md_contents:
            notebook = jupytext.reads(md_contents, fmt='md')
            jupytext.write(notebook, output_file, fmt='ipynb')
    
    return True
