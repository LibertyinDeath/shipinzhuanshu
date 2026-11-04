#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""build_article.py —— 视频转文案 · 第 4 步：合并成能读的文章（去时间戳）

用法：
    python build_article.py <工作目录> [--chapters 章节.json] [--title 标题] [--source 来源] [--out 输出.md]

前置：postprocess.py 已产出 segments_fixed.json
章节.json 可选，格式：[{"start": 0, "title": "开场"}, {"start": 600, "title": "第一部分"}, ...]

断句规则（2026-11-03 实战调出来的，改动前先读 SKILL.md）：
- 前一段没有句末标点 → 用逗号连接；已经有标点 → 直接拼
- 静默 >3.5s 且已攒 10 字以上 → 断句
- 已攒 90 字且静默 >1.2s → 断句
- 单句 >70 字，在 20~55 字之间的逗号处切开
- 段落攒到 220 字左右断段
- 只补标点，不改字、不润色；口误与重复保留
"""
import argparse
import json
import os
import re


def split_long(s):
    out = []
    while len(s) > 70:
        cut = -1
        for m in re.finditer(r"[，；]", s):
            if 20 <= m.start() <= 55:
                cut = m.start()
        if cut < 0:
            break
        out.append(s[:cut])
        s = s[cut + 1:]
    out.append(s)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--chapters")
    ap.add_argument("--title", default="")
    ap.add_argument("--source", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    path = os.path.join(args.workdir, "segments_fixed.json")
    if not os.path.isfile(path):
        raise SystemExit("找不到 segments_fixed.json，先跑 postprocess.py")
    rows = json.load(open(path, encoding="utf-8"))

    # 1) 合并成句，保留起始时间
    raw = []          # [(start, text)]
    buf = ""
    buf_start = 0.0
    prev_end = None
    for r in rows:
        t = (r.get("text") or "").strip(" ，、")
        if not t:
            continue
        gap = (r["start"] - prev_end) if prev_end is not None else 99
        if buf and ((gap > 3.5 and len(buf) >= 10) or (len(buf) >= 90 and gap > 1.2)):
            raw.append((buf_start, buf))
            buf = ""
        if not buf:
            buf, buf_start = t, r["start"]
        elif re.search(r"[。？！，；：]$", buf):
            buf += t
        else:
            buf += "，" + t
        prev_end = r["end"]
        if re.search(r"[。？！…]$", t):
            raw.append((buf_start, buf))
            buf = ""
    if buf:
        raw.append((buf_start, buf))

    # 2) 补句末标点 + 超长句切分
    pieces = []       # [(start, text)]
    for st, s in raw:
        s = s.strip(" ，、")
        if not s:
            continue
        for piece in split_long(s):
            piece = piece.strip(" ，、")
            if not piece:
                continue
            if not re.search(r"[。？！…]$", piece):
                piece += "？" if re.search(r"(吗|呢)$", piece) else "。"
            pieces.append((st, piece))

    chapters = []
    if args.chapters and os.path.isfile(args.chapters):
        chapters = sorted(json.load(open(args.chapters, encoding="utf-8")),
                          key=lambda c: c["start"])

    lines = []
    if args.title:
        lines.append("# %s\n" % args.title)
        if args.source:
            lines.append("> 来源：%s" % args.source)
        lines.append("> 整理原则：保留讲者口语与现场互动，只修正转写错字、补断句标点、去掉时间戳，未改写、未润色。\n")
        lines.append("---\n")

    ci = -1
    para = []
    plen = 0
    for st, piece in pieces:
        while ci + 1 < len(chapters) and st >= chapters[ci + 1]["start"]:
            if para:
                lines.append("".join(para) + "\n")
                para, plen = [], 0
            ci += 1
            lines.append("\n## %s\n" % chapters[ci]["title"])
        para.append(piece)
        plen += len(piece)
        if plen >= 220:
            lines.append("".join(para) + "\n")
            para, plen = [], 0
    if para:
        lines.append("".join(para) + "\n")

    body = "\n".join(lines).strip() + "\n"
    out = args.out or os.path.join(args.workdir, "文案_口语全文版.md")
    open(out, "w", encoding="utf-8").write(body)
    print("句子 %d 条 / %d 字 → %s" % (len(pieces), sum(len(x[1]) for x in pieces), out))


if __name__ == "__main__":
    main()
