def parse_docx(doc_path):
    try:
        from docx import Document as DocDocument
        from tabulate import tabulate
    except BaseException as e:
        raise_not_install("You must install 'python-docx' and 'tabulate' !")

    doc = DocDocument(doc_path)
    markdown_str = ""
    for element in doc.element.body:
        if element.tag.endswith('tbl'):
            table = Table(element, doc)
            data = [[cell.text for cell in row.cells] for row in table.rows]
            markdown_str += "\n" + tabulate(data, tablefmt="pipe")
        elif element.tag.endswith('p'):
            paragraph = Paragraph(element, doc)
            style_name = paragraph.style.name
            if style_name.startswith('Heading') or style_name.startswith('标题'):
                markdown_str += "\n" + "#" * int(re.findall(r'\d+', paragraph.style.name)[0]) + " " + paragraph.text
            else:
                markdown_str += "\n" + paragraph.text

    md_file_path = os.path.splitext(doc_path)[0] + ".md"
    with open(md_file_path, 'w') as md_file:
        md_file.write(markdown_str)

    return md_file_path
  