import mistune
from ..importer import load_markdown

def export_html(input_file: str, output_file: str):
    if input_file:
        if not output_file:
            output_file = input_file + ".html"

        md_contents = ''
        docs = load_markdown(input_file)

        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        if docs.markdown:
            html = mistune.html(docs.markdown)
            with open(output_file, 'w') as f:
                f.write(html)
    
    return True
