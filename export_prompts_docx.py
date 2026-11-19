"""生成“对话提示词记录”Word 文档。"""

from __future__ import annotations

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

INK = RGBColor(0x14, 0x28, 0x3C)
INK_SOFT = RGBColor(0x3E, 0x55, 0x6B)
MUTED = RGBColor(0x70, 0x84, 0x96)
ACCENT = RGBColor(0x0B, 0x6E, 0x8C)
ACCENT_LIGHT = "E8F4F7"
BOX_FILL = "F5F8FA"
LINE = "D6E1E8"

PROMPTS = [
    (
        "小数转换功能",
        "现在你是一个程序工作者，你的任务是让这个进制转换器能够转换小数",
        "为进制转换器增加小数与循环小数支持。",
    ),
    (
        "打包可执行文件",
        "现在生成一个能直接打开的exe文件",
        "将 v1.2.0 打包为无需安装 Python、双击即可运行的 Windows 程序。",
    ),
    (
        "导出提示词",
        "把我和你说话的提示词导出文档",
        "把本次会话中用户发送的提示词整理并导出为文档。",
    ),
]


def set_run_font(run, size: float, *, bold: bool = False, color=INK, name="微软雅黑"):
    run.font.name = name
    run.font.size = Pt(size)
    run.bold = bold
    run.font.color.rgb = color
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), name)
    rfonts.set(qn("w:hAnsi"), name)
    rfonts.set(qn("w:eastAsia"), name)


def add_bottom_border(paragraph, color: str = "0B6E8C", size: int = 12):
    ppr = paragraph._p.get_or_add_pPr()
    pbdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size))
    bottom.set(qn("w:space"), "6")
    bottom.set(qn("w:color"), color)
    pbdr.append(bottom)
    ppr.append(pbdr)


def shade_cell(cell, fill: str):
    tcpr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcpr.append(shd)


def set_cell_margins(cell, top=120, start=180, bottom=120, end=180):
    tcpr = cell._tc.get_or_add_tcPr()
    margins = OxmlElement("w:tcMar")
    for edge, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = OxmlElement(f"w:{edge}")
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")
        margins.append(node)
    tcpr.append(margins)


def set_cell_borders(cell, *, color: str = LINE, left=None):
    tcpr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        node = OxmlElement(f"w:{edge}")
        if edge == "left" and left:
            node.set(qn("w:val"), "single")
            node.set(qn("w:sz"), "24")
            node.set(qn("w:space"), "0")
            node.set(qn("w:color"), left)
        elif edge == "left":
            node.set(qn("w:val"), "nil")
        else:
            node.set(qn("w:val"), "single")
            node.set(qn("w:sz"), "4")
            node.set(qn("w:space"), "0")
            node.set(qn("w:color"), color)
        borders.append(node)
    tcpr.append(borders)


def set_col_widths(table, widths):
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    tblpr = table._tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblpr.append(layout)
    for row in table.rows:
        for index, width in enumerate(widths):
            row.cells[index].width = width


def add_page_number_footer(section):
    footer = section.footer
    paragraph = footer.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run("进制转换演示器 · 对话提示词记录　　")
    set_run_font(run, 8.5, color=MUTED)
    run = paragraph.add_run("第 ")
    set_run_font(run, 8.5, color=MUTED)
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)
    set_run_font(run, 8.5, color=MUTED)
    run = paragraph.add_run(" 页")
    set_run_font(run, 8.5, color=MUTED)


def main():
    document = Document()
    section = document.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.2)
    section.right_margin = Cm(2.2)
    section.header_distance = Cm(1.2)
    section.footer_distance = Cm(1.0)

    normal = document.styles["Normal"]
    normal.font.name = "微软雅黑"
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = INK
    normal.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "微软雅黑")
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.line_spacing = 1.35

    add_page_number_footer(section)

    # 页眉标识
    eyebrow = document.add_paragraph()
    eyebrow.paragraph_format.space_before = Pt(6)
    eyebrow.paragraph_format.space_after = Pt(10)
    run = eyebrow.add_run("P R O M P T   A R C H I V E   /   2 0 2 6 - 1 1 - 1 9")
    set_run_font(run, 7.5, bold=True, color=ACCENT)

    title = document.add_paragraph()
    title.paragraph_format.space_after = Pt(4)
    run = title.add_run("对话提示词记录")
    set_run_font(run, 26, bold=True, color=INK)

    subtitle = document.add_paragraph()
    subtitle.paragraph_format.space_after = Pt(14)
    run = subtitle.add_run("进制转换演示器 · 与 AI 编程助手的会话")
    set_run_font(run, 11.5, color=INK_SOFT)

    rule = document.add_paragraph()
    rule.paragraph_format.space_after = Pt(18)
    add_bottom_border(rule, size=14)

    # 元信息表
    meta = document.add_table(rows=4, cols=2)
    meta.style = "Table Grid"
    meta_data = [
        ("项目名称", "进制转换演示器（Base Conversion Explorer）"),
        ("会话日期", "2026 年 11 月 19 日"),
        ("提示词条数", "3 条（按发送顺序排列）"),
        ("记录范围", "仅用户发送的提示词原文；不含系统指令、运行环境信息、工具调用与助手回复"),
    ]
    for row_index, (key, value) in enumerate(meta_data):
        key_cell, value_cell = meta.rows[row_index].cells
        shade_cell(key_cell, "EEF3F6")
        set_cell_margins(key_cell, top=90, bottom=90)
        set_cell_margins(value_cell, top=90, bottom=90)
        key_cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        value_cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        key_paragraph = key_cell.paragraphs[0]
        key_run = key_paragraph.add_run(key)
        set_run_font(key_run, 9, bold=True, color=INK_SOFT)
        value_paragraph = value_cell.paragraphs[0]
        value_run = value_paragraph.add_run(value)
        set_run_font(value_run, 9.5, color=INK)
    set_col_widths(meta, [Cm(3.4), Cm(13.2)])

    # 提示词卡片
    heading = document.add_paragraph()
    heading.paragraph_format.space_before = Pt(22)
    heading.paragraph_format.space_after = Pt(10)
    run = heading.add_run("提示词原文")
    set_run_font(run, 15, bold=True, color=INK)

    for index, (label, prompt, note) in enumerate(PROMPTS, start=1):
        card_heading = document.add_paragraph()
        if index == 3:
            # 第 3 条与说明另起一页，避免卡片被分页拆开。
            card_heading.paragraph_format.page_break_before = True
        card_heading.paragraph_format.space_before = Pt(12)
        card_heading.paragraph_format.space_after = Pt(6)
        number = card_heading.add_run(f"{index:02d}")
        set_run_font(number, 16, bold=True, color=ACCENT)
        spacer = card_heading.add_run("　")
        set_run_font(spacer, 10)
        title_run = card_heading.add_run(label)
        set_run_font(title_run, 12, bold=True, color=INK)
        if index == 3:
            suffix = card_heading.add_run("　·　本次导出请求")
            set_run_font(suffix, 8.5, color=MUTED)

        quote = document.add_table(rows=1, cols=1)
        quote.alignment = WD_TABLE_ALIGNMENT.CENTER
        cell = quote.rows[0].cells[0]
        shade_cell(cell, BOX_FILL)
        set_cell_borders(cell, color=LINE, left="0B6E8C")
        set_cell_margins(cell, top=160, start=240, bottom=160, end=240)
        cell.width = Cm(16.6)
        paragraph = cell.paragraphs[0]
        paragraph.paragraph_format.line_spacing = 1.5
        run = paragraph.add_run(prompt)
        set_run_font(run, 12.5, color=INK)

        note_paragraph = document.add_paragraph()
        note_paragraph.paragraph_format.space_before = Pt(4)
        note_paragraph.paragraph_format.space_after = Pt(6)
        note_label = note_paragraph.add_run("整理者注：")
        set_run_font(note_label, 8.5, bold=True, color=MUTED)
        note_run = note_paragraph.add_run(note)
        set_run_font(note_run, 8.5, color=MUTED)

    # 记录说明
    heading = document.add_paragraph()
    heading.paragraph_format.space_before = Pt(20)
    heading.paragraph_format.space_after = Pt(8)
    run = heading.add_run("记录说明")
    set_run_font(run, 13, bold=True, color=INK)

    notes = [
        "本文件只包含用户发送的提示词，不包含系统指令、环境信息、工具调用与助手回复。",
        "提示词按会话中的发送顺序排列，标点、大小写和措辞均保持原样。",
        "“整理者注”是导出时补充的任务说明，不属于提示词原文。",
    ]
    for text in notes:
        paragraph = document.add_paragraph(style="List Bullet")
        paragraph.paragraph_format.space_after = Pt(3)
        paragraph.paragraph_format.left_indent = Cm(0.65)
        paragraph.paragraph_format.first_line_indent = Cm(-0.35)
        run = paragraph.add_run(text)
        set_run_font(run, 9.5, color=INK_SOFT)

    final = document.add_paragraph()
    final.paragraph_format.space_before = Pt(18)
    run = final.add_run("文档生成：DeepSeek Harness　·　2026-11-19")
    set_run_font(run, 8, color=MUTED)

    document.core_properties.title = "对话提示词记录"
    document.core_properties.subject = "进制转换演示器会话中的用户提示词"
    document.core_properties.author = "DeepSeek Harness"
    document.core_properties.comments = "仅记录用户发送的提示词原文。"

    output = "对话提示词记录.docx"
    document.save(output)
    print(output)


if __name__ == "__main__":
    main()
