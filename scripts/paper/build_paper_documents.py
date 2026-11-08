"""Create editable manuscript and one-page team-summary DOCX files from reviewed text.

Requires python-docx. Render the outputs with the documents skill's render_docx.py
and inspect every page before delivering; this script does not substitute for QA.
"""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / "docs/paper"
MATH = {
    "10w/A": ("", "10w", "A", ""),
    "NDVI = (B08 − B04)/(B08 + B04)": ("NDVI = ", "B08 − B04", "B08 + B04", ""),
    "GCVI = B08/B03 − 1": ("GCVI = ", "B08", "B03", " − 1"),
    "NDVI705 = (B08 − B05)/(B08 + B05)": ("NDVI705 = ", "B08 − B05", "B08 + B05", ""),
    "NDVI740 = (B08 − B06)/(B08 + B06)": ("NDVI740 = ", "B08 − B06", "B08 + B06", ""),
    "MTCI-labelled ratio = (B08 − B05)/(B05 − B04)": ("MTCI-labelled ratio = ", "B08 − B05", "B05 − B04", ""),
}
TOKEN = re.compile("(" + "|".join(re.escape(s) for s in MATH) + r"|\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))")


def set_font(font, size, bold=False):
    font.name = "Times New Roman"
    font.size = Pt(size)
    font.bold = bold
    font.color.rgb = RGBColor(0, 0, 0)


def math_run(text):
    run = OxmlElement("m:r")
    prop = OxmlElement("m:rPr")
    style = OxmlElement("m:sty")
    style.set(qn("m:val"), "p")
    prop.append(style)
    run.append(prop)
    node = OxmlElement("m:t")
    node.set(qn("xml:space"), "preserve")
    node.text = text
    run.append(node)
    return run


def equation(paragraph, spec):
    before, numerator, denominator, after = spec
    math = OxmlElement("m:oMath")
    if before:
        math.append(math_run(before))
    fraction = OxmlElement("m:f")
    for name, value in [("num", numerator), ("den", denominator)]:
        part = OxmlElement(f"m:{name}")
        part.append(math_run(value))
        fraction.append(part)
    math.append(fraction)
    if after:
        math.append(math_run(after))
    paragraph._p.append(math)


def hyperlink(paragraph, label, url):
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), paragraph.part.relate_to(
        url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True))
    run = OxmlElement("w:r")
    properties = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "17365D")
    properties.append(color)
    run.append(properties)
    node = OxmlElement("w:t")
    node.text = label
    run.append(node)
    link.append(run)
    paragraph._p.append(link)


def inline(paragraph, text):
    for token in TOKEN.split(text):
        if not token:
            continue
        if token in MATH:
            equation(paragraph, MATH[token])
        elif token.startswith("**"):
            paragraph.add_run(token[2:-2]).bold = True
        elif token.startswith("`"):
            paragraph.add_run(token[1:-1])
        elif token.startswith("[") and "](" in token:
            label, url = token[1:-1].split("](", 1)
            hyperlink(paragraph, label, url)
        else:
            paragraph.add_run(token)


def add_table(document, lines, compact):
    cells = [[v.strip() for v in line.strip().strip("|").split("|")] for line in lines]
    rows = [cells[0]] + [r for r in cells[1:] if not all(re.fullmatch(r":?-+:?", c) for c in r)]
    count = len(rows[0])
    table = document.add_table(rows=0, cols=count)
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    widths = [4.75, .925, .925] if compact else [1.37, .78, 1.3, 3.05]
    for column, width in zip(table.columns, widths, strict=True):
        column.width = Inches(width)
    props = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ["top", "left", "bottom", "right", "insideH", "insideV"]:
        item = OxmlElement(f"w:{edge}")
        for key, value in {"val": "single", "sz": "4", "color": "D9D9D9"}.items():
            item.set(qn(f"w:{key}"), value)
        borders.append(item)
    props.append(borders)
    for number, values in enumerate(rows):
        row = table.add_row()
        tr = row._tr.get_or_add_trPr()
        tr.append(OxmlElement("w:cantSplit"))
        if number == 0:
            tr.append(OxmlElement("w:tblHeader"))
        for col, (cell, value, width) in enumerate(zip(row.cells, values, widths, strict=True)):
            cell.width = Inches(width)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tc = cell._tc.get_or_add_tcPr()
            margins = OxmlElement("w:tcMar")
            for edge in ["top", "left", "bottom", "right"]:
                item = OxmlElement(f"w:{edge}")
                item.set(qn("w:w"), "55" if compact else "75")
                item.set(qn("w:type"), "dxa")
                margins.append(item)
            tc.append(margins)
            if number == 0:
                shade = OxmlElement("w:shd")
                shade.set(qn("w:fill"), "E9EDF2")
                tc.append(shade)
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = 1.0
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if col in [1, 2] else WD_ALIGN_PARAGRAPH.LEFT
            if number == 0:
                paragraph.paragraph_format.keep_with_next = True
            inline(paragraph, value)
            for run in paragraph.runs:
                set_font(run.font, 10.5 if compact else 10, number == 0)
    document.add_paragraph().paragraph_format.space_after = Pt(0)


def build(source, target, compact=False):
    document = Document()
    section = document.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = section.bottom_margin = Inches(.65 if compact else .8)
    section.left_margin = section.right_margin = Inches(.95 if compact else 1)
    section.header_distance = section.footer_distance = Inches(.3)
    style = document.styles["Normal"]
    set_font(style.font, 11)
    style.paragraph_format.line_spacing = 1.03 if compact else 1.08
    style.paragraph_format.space_after = Pt(5 if compact else 6)
    style.paragraph_format.widow_control = True
    reference_style = document.styles.add_style("Paper Reference", WD_STYLE_TYPE.PARAGRAPH)
    reference_style.base_style = style
    set_font(reference_style.font, 10.5)
    reference_style.paragraph_format.line_spacing = 1.0
    reference_style.paragraph_format.space_after = Pt(3)
    reference_style.paragraph_format.left_indent = Inches(.24)
    reference_style.paragraph_format.first_line_indent = Inches(-.24)
    for name, size in [("Title", 16), ("Subtitle", 10), ("Heading 1", 12), ("Heading 2", 11)]:
        s = document.styles[name]
        set_font(s.font, size, name != "Subtitle")
        s.font.underline = False
        s.paragraph_format.space_before = Pt(0 if name == "Title" else 10)
        s.paragraph_format.space_after = Pt(7 if name == "Title" else 5)
        s.paragraph_format.keep_with_next = True
        for border in list(s.element.xpath(".//w:pBdr")):
            border.getparent().remove(border)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if compact:
        r = footer.add_run("Felix and Florian · Results through 7 November 2026")
        set_font(r.font, 9)
    else:
        r = footer.add_run("Zimbabwe maize yield estimation  |  ")
        set_font(r.font, 9)
        field = OxmlElement("w:fldSimple")
        field.set(qn("w:instr"), "PAGE")
        footer._p.append(field)
    lines = source.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].startswith("|"):
                table_lines.append(lines[i]); i += 1
            add_table(document, table_lines, compact)
            continue
        if line.startswith("# "):
            inline(document.add_paragraph(style="Title"), line[2:])
        elif line.startswith("## "):
            inline(document.add_paragraph(style="Heading 1"), line[3:])
        elif line.startswith("### "):
            inline(document.add_paragraph(style="Heading 2"), line[4:])
        else:
            text = line
            while i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].startswith(("|", "#")):
                i += 1
                text += " " + lines[i]
            p = document.add_paragraph()
            if text.startswith("Table 1."):
                p.paragraph_format.keep_with_next = True
            if re.match(r"^\[\d+\] ", text):
                p.style = reference_style
            inline(p, text)
        i += 1
    document.core_properties.author = "Felix Yu and Florian Saewert"
    document.core_properties.title = lines[0].removeprefix("# ")
    document.core_properties.subject = "Data sources and preparation" if not compact else "Results for team integration"
    document.core_properties.keywords = "Zimbabwe, maize yield, crop cuts, Sentinel-2, NASA POWER"
    document.core_properties.comments = "Prepared from the reviewed repository text and frozen experiment outputs."
    document.save(target)
    print(target)


if __name__ == "__main__":
    build(PAPER / "DATA_SOURCES_AND_PREPARATION.md", PAPER / "data_sources_and_preparation.docx")
    build(PAPER / "RESULTS_SUMMARY.md", PAPER / "results_summary_one_page.docx", compact=True)
