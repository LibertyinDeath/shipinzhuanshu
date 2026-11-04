#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""build_epub.py —— 过钱关成书打包（EPUB3 + MD 单文件，纯 Python 标准库）

目录规范（2026-11-04 宝总定）：
- 目录不显示「第N章」前缀，只显示内容标题（章 + 小节两级都进目录）
- 章页正文大标题同样不带章号
- 加粗用 <strong> 正常渲染，不做二次转义
用法：python build_epub.py
输出：99-成书/《过钱关·创富智慧》（试读版·卷一）.epub + 同名 .md
加卷/加章只改 MANIFEST。
"""
import html
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
CH = BASE / "chapters"

BOOK_TITLE = "过钱关·创富智慧"
BOOK_AUTHOR = "剽悍一只猫（猫叔）· 课程主讲"
VERSION_TAG = "试读版·卷一·目录修订2"
LANG = "zh-CN"
UUID = "urn:uuid:guoqian-guan-book-v1-2026-11-04-tocfix3"

# 分卷结构（章文件按文件名排序；章文件内 H1 为章标题，## 为小节）
MANIFEST = [
    ("卷一·先导：创富精读营", CH / "卷一-先导"),
]

CSS = """body { margin: 0.5em 1em; line-height: 1.7; }
h1 { font-size: 1.5em; margin: 1em 0 0.8em; }
h2 { font-size: 1.2em; margin: 1.2em 0 0.6em; }
p { text-indent: 2em; text-align: justify; margin: 0.4em 0; }
blockquote { background: #f5f5f0; border-left: 4px solid #c8b273;
  margin: 0.8em 0; padding: 0.6em 0.9em; }
blockquote p { text-indent: 0; }
strong { color: #8a2b0e; }
.vol { text-align: center; margin-top: 6em; }
.vol h1 { font-size: 1.8em; }
.intro { text-indent: 0; font-size: 0.9em; color: #555; }
img.cover { max-width: 100%; max-height: 100%; }
"""


def inline(text: str) -> str:
    """**加粗** → <strong>（先打标记再转义，避免二次转义吃掉标签）。"""
    text = re.sub(r"\*\*(.+?)\*\*", lambda m: "\x01%s\x02" % m.group(1), text)
    text = html.escape(text, quote=False)
    return text.replace("\x01", "<strong>").replace("\x02", "</strong>")


def md_to_xhtml(md_text: str) -> str:
    """覆盖书里用到的语法：H1/H2、引用块、加粗、列表、段落。"""
    out = []
    in_quote = False
    in_list = False

    def close_all():
        nonlocal in_quote, in_list
        if in_quote:
            out.append("</blockquote>")
            in_quote = False
        if in_list:
            out.append("</ul>")
            in_list = False

    for raw in md_text.splitlines():
        s = raw.strip()
        if not s:
            close_all()
            continue
        if s.startswith("# "):
            close_all()
            out.append("<h1>%s</h1>" % inline(s[2:]))
        elif s.startswith("## "):
            close_all()
            out.append("<h2>%s</h2>" % inline(s[3:]))
        elif s.startswith("> "):
            if in_list:
                out.append("</ul>")
                in_list = False
            if not in_quote:
                out.append("<blockquote>")
                in_quote = True
            out.append("<p>%s</p>" % inline(s[2:]))
        elif re.match(r"^([-*]|\d+\.)\s+", s):
            close_all()
            if not in_list:
                out.append("<ul>")
                in_list = True
            item = re.sub(r"^([-*]|\d+\.)\s+", "", s)
            out.append("<li>%s</li>" % inline(item))
        else:
            close_all()
            out.append("<p>%s</p>" % inline(s))
    close_all()
    return "\n".join(out)


def strip_ch_prefix(title: str) -> str:
    """去掉「第N章」前缀——目录与正文都只留内容标题。"""
    return re.sub(r"^第\d+章\s*", "", title).strip()


def chapter_files():
    """[(卷名, [(内容标题, 处理后的md, [小节标题...]), ...]), ...]"""
    vols = []
    for vol_name, vdir in MANIFEST:
        chapters = []
        for f in sorted(vdir.glob("*.md")):
            md = f.read_text(encoding="utf-8")
            m = re.match(r"^#\s+(.+)", md)
            raw_title = m.group(1).strip() if m else f.stem
            title = strip_ch_prefix(raw_title)
            body = md.split("\n", 1)[1] if md.startswith("# ") else md
            fixed = "# %s\n%s" % (title, body)
            sections = [s[3:].strip()
                        for s in md.splitlines() if s.startswith("## ")]
            chapters.append((title, fixed, sections))
        vols.append((vol_name, chapters))
    return vols


def page(title, body) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE html>\n<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-CN">'
        '<head><meta charset="utf-8"/><title>%s</title>'
        '<link rel="stylesheet" type="text/css" href="style.css"/></head>'
        '<body>\n%s\n</body></html>'
    ) % (html.escape(title), body)


def build_epub(vols, out_path: Path):
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    opf_items = []
    spine = []
    ncx_points = []
    order = 0

    def add_item(idref, href, media, spine_flag=False):
        opf_items.append((idref, href, media))
        if spine_flag:
            spine.append(idref)

    cover_xhtml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE html>\n<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-CN">'
        '<head><meta charset="utf-8"/><title>%s</title>'
        '<link rel="stylesheet" type="text/css" href="style.css"/></head><body>'
        '<div style="text-align:center;">'
        '<img class="cover" src="cover.png" alt="%s"/></div></body></html>'
    ) % (BOOK_TITLE, BOOK_TITLE)
    add_item("cover", "cover.xhtml", "application/xhtml+xml", spine_flag=True)
    add_item("cover-img", "cover.png", "image/png")

    files_to_write = {"OEBPS/cover.xhtml": cover_xhtml}
    nav_lis = []

    for vi, (vol_name, chapters) in enumerate(vols, 1):
        vol_id = f"vol{vi}"
        add_item(vol_id, f"vol{vi}.xhtml", "application/xhtml+xml", spine_flag=True)
        files_to_write[f"OEBPS/vol{vi}.xhtml"] = page(
            vol_name, '<div class="vol"><h1>%s</h1></div>' % html.escape(vol_name))

        order += 1
        vol_ncx = {"id": f"np{order}", "order": order, "text": vol_name,
                   "src": f"vol{vi}.xhtml", "children": []}
        ncx_points.append(vol_ncx)

        ol = []
        for ci, (title, md, sections) in enumerate(chapters, 1):
            cid = f"ch{vi:02d}{ci:02d}"
            href = f"ch{vi:02d}{ci:02d}.xhtml"
            files_to_write[f"OEBPS/{href}"] = page(title, md_to_xhtml(md))
            add_item(cid, href, "application/xhtml+xml", spine_flag=True)
            # nav：小节嵌在章 li 内
            sec_lis = "".join('<li><a href="%s">%s</a></li>' % (href, html.escape(s))
                              for s in sections)
            ol.append('<li><a href="%s">%s</a>%s</li>'
                      % (href, html.escape(title),
                         ("<ol>%s</ol>" % sec_lis) if sections else ""))
            # ncx
            order += 1
            ch_ncx = {"id": f"np{order}", "order": order, "text": title,
                      "src": href, "children": []}
            vol_ncx["children"].append(ch_ncx)
            for sec in sections:
                order += 1
                ch_ncx["children"].append(
                    {"id": f"np{order}", "order": order, "text": sec,
                     "src": href, "children": []})
        nav_lis.append('<li><a href="vol%d.xhtml">%s</a><ol>%s</ol></li>'
                       % (vi, html.escape(vol_name), "".join(ol)))

    def ncx_xml(points):
        buf = []
        for p in points:
            kids = ncx_xml(p["children"]) if p["children"] else ""
            buf.append(
                '<navPoint id="%s" playOrder="%d"><navLabel><text>%s</text></navLabel>'
                '<content src="%s"/>%s</navPoint>'
                % (p["id"], p["order"], html.escape(p["text"]), p["src"], kids))
        return "".join(buf)

    # 目录文件必须登记进 manifest（EPUB3 规范）：nav 带 properties="nav"，
    # ncx 用 application/x-dtbncx+xml——否则阅读器读不到目录，自己按文件编号
    add_item("nav", "nav.xhtml", "application/xhtml+xml")
    add_item("ncx", "toc.ncx", "application/x-dtbncx+xml")

    nav_xhtml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE html>\n<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN">'
        '<head><meta charset="utf-8"/><title>目录</title>'
        '<link rel="stylesheet" type="text/css" href="style.css"/></head><body>'
        '<nav epub:type="toc" id="toc"><h1>目录</h1><ol>%s</ol></nav></body></html>'
    ) % "".join(nav_lis)
    ncx = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
        '<head><meta name="dtb:uid" content="%s"/><meta name="dtb:depth" content="3"/>'
        '<meta name="dtb:totalPageCount" content="0"/><meta name="dtb:maxPageNumber" content="0"/></head>'
        '<docTitle><text>%s</text></docTitle><navMap>%s</navMap></ncx>'
    ) % (UUID, BOOK_TITLE, ncx_xml(ncx_points))
    opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:identifier id="bookid">%s</dc:identifier>'
        '<dc:title>%s</dc:title>'
        '<dc:creator>%s</dc:creator>'
        '<dc:language>%s</dc:language>'
        '<dc:description>%s</dc:description>'
        '<meta property="dcterms:modified">%s</meta></metadata>'
        '<manifest>%s</manifest>'
        '<spine toc="ncx">%s</spine></package>'
    ) % (UUID, html.escape(BOOK_TITLE), html.escape(BOOK_AUTHOR), LANG,
         html.escape("整理自过钱关特训营课程转写稿（忠实原意整理版）"),
         modified,
         "".join(
             ('<item id="%s" href="%s" media-type="%s" properties="%s"/>' % (t[0], t[1], t[2], prop))
             if (prop := {"cover-img": "cover-image", "nav": "nav"}.get(t[0])) else
             ('<item id="%s" href="%s" media-type="%s"/>' % t)
             for t in opf_items),
         "".join('<itemref idref="%s"/>' % s for s in spine))
    # spine 加 toc 属性，兼容按 EPUB2 方式找目录的阅读器

    with zipfile.ZipFile(out_path, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip",
                   compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0" encoding="utf-8"?>\n'
                   '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OEBPS/content.opf" '
                   'media-type="application/oebps-package+xml"/></rootfiles></container>')
        z.writestr("OEBPS/style.css", CSS)
        z.writestr("OEBPS/cover.png", (BASE / "cover.png").read_bytes())
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/nav.xhtml", nav_xhtml)
        z.writestr("OEBPS/toc.ncx", ncx)
        for path, content in files_to_write.items():
            z.writestr(path, content)


def build_md(vols, out_path: Path):
    parts = ["# %s（%s）\n" % (BOOK_TITLE, VERSION_TAG),
             "> 主讲：%s ｜ 整理自过钱关特训营课程转写稿，忠实原意整理版\n" % BOOK_AUTHOR]
    for vol_name, chapters in vols:
        parts.append("\n\n# 【%s】\n" % vol_name)
        for title, md, _ in chapters:
            body = md.split("\n", 1)[1] if md.startswith("# ") else md
            parts.append("\n\n## %s\n" % title)
            parts.append(body.strip())
    out_path.write_text("".join(parts), encoding="utf-8")


def validate(out_path: Path):
    import xml.etree.ElementTree as ET
    bad = []
    with zipfile.ZipFile(out_path) as z:
        for name in z.namelist():
            if name.endswith((".xhtml", ".opf", ".ncx")):
                try:
                    ET.fromstring(z.read(name))
                except ET.ParseError as e:
                    bad.append((name, str(e)))
    return bad


if __name__ == "__main__":
    vols = chapter_files()
    n = sum(len(c) for _, c in vols)
    secs = sum(len(s) for _, chs in vols for _, _, s in chs)
    total = sum(len(md) for _, chs in vols for _, md, _ in chs)
    print("卷数 %d，章数 %d，小节 %d，总字符 %d" % (len(vols), n, secs, total))
    epub_path = BASE / ("《%s》（%s）.epub" % (BOOK_TITLE, VERSION_TAG))
    md_path = BASE / ("《%s》（%s）.md" % (BOOK_TITLE, VERSION_TAG))
    build_epub(vols, epub_path)
    build_md(vols, md_path)
    bad = validate(epub_path)
    if bad:
        print("✗ XML 校验失败：", bad)
        raise SystemExit(1)
    print("✓ XML 全量校验通过")
    print("EPUB:", epub_path, "(%.1f MB)" % (epub_path.stat().st_size / 1048576))
    print("MD  :", md_path)
