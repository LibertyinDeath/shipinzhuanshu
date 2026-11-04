#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""postprocess.py —— 视频转文案 · 第 3 步：繁简统一 + 中文标点 + 术语校正

用法：
    python postprocess.py <工作目录> [--terms 术语表.tsv] [--chapters 章节.json]

输出：
    segments_fixed.json   清洗后的分段（含 start/end）
    plain.txt             每行 [HH:MM:SS] 文本，便于人眼快速扫读
    全文逐字稿.md          带时间码与章节的完整稿

术语表格式（TSV，一行一条，# 开头为注释）：
    破军	破局
    班农老师	班主任
口诀：长的放前面，避免短词先命中把长词拆坏。
"""
import argparse
import json
import os
import re
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TERMS = os.path.join(SKILL_DIR, "scripts", "terms_default.txt")


def load_terms(*paths):
    pairs = []
    for p in paths:
        if not p or not os.path.isfile(p):
            continue
        for line in open(p, encoding="utf-8-sig"):
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 2 and parts[0]:
                pairs.append((parts[0], parts[1]))
    # 长串优先，防止短词先把长词切碎
    pairs.sort(key=lambda x: -len(x[0]))
    return pairs


def to_simplified(t):
    try:
        import zhconv
        return zhconv.convert(t, "zh-cn")
    except Exception:
        return t


def fix_punct(t):
    t = t.strip()
    t = re.sub(r"(?<=[\u4e00-\u9fa5])\s*,\s*", "，", t)
    t = re.sub(r"(?<=[\u4e00-\u9fa5])\s*\.\s*", "。", t)
    t = re.sub(r"(?<=[\u4e00-\u9fa5])\s*\?\s*", "？", t)
    t = re.sub(r"(?<=[\u4e00-\u9fa5])\s*!\s*", "！", t)
    t = re.sub(r"(?<=[\u4e00-\u9fa5])\s*;\s*", "；", t)
    t = re.sub(r"(?<=[\u4e00-\u9fa5])\s*:\s*", "：", t)
    t = re.sub(r"(?<=[0-9A-Za-z])\s*,\s*(?=[\u4e00-\u9fa5])", "，", t)
    t = re.sub(r",。", "。", t)
    t = re.sub(r"，{2,}", "，", t)
    return t


def hhmmss(s):
    s = int(float(s))
    return "%02d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--terms", action="append", default=[])
    ap.add_argument("--chapters")
    ap.add_argument("--title", default="全文逐字稿")
    args = ap.parse_args()

    src = os.path.join(args.workdir, "segments.jsonl")
    if not os.path.isfile(src):
        raise SystemExit("找不到 segments.jsonl，先跑 transcribe.py")

    term_files = list(args.terms) + [os.path.join(args.workdir, "terms.tsv"), DEFAULT_TERMS]
    terms = load_terms(*term_files)
    print("术语表 %d 条" % len(terms))

    rows = [json.loads(l) for l in open(src, encoding="utf-8") if l.strip()]
    out = []
    for r in rows:
        t = to_simplified(r.get("text", "")).strip()
        t = fix_punct(t)
        for a, b in terms:
            t = t.replace(a, b)
        t = t.strip(" ，、")
        if not t:
            continue
        out.append({"start": r["start"], "end": r["end"], "text": t})

    json.dump(out, open(os.path.join(args.workdir, "segments_fixed.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=0)

    with open(os.path.join(args.workdir, "plain.txt"), "w", encoding="utf-8") as f:
        for x in out:
            f.write("[%s] %s\n" % (hhmmss(x["start"]), x["text"]))

    chapters = []
    if args.chapters and os.path.isfile(args.chapters):
        chapters = json.load(open(args.chapters, encoding="utf-8"))
        chapters.sort(key=lambda c: c["start"])

    lines = ["# %s\n" % args.title,
             "> 机器转写稿：繁简已统一、标点已补齐、专有名词已按术语表校正，保留口语原样。\n"]
    ci = -1
    for x in out:
        while ci + 1 < len(chapters) and x["start"] >= chapters[ci + 1]["start"]:
            ci += 1
            lines.append("\n## %s（%s 起）\n" % (chapters[ci]["title"], hhmmss(chapters[ci]["start"])))
        lines.append("**[%s - %s]** %s" % (hhmmss(x["start"]), hhmmss(x["end"]), x["text"]))
    lines.append("\n---\n\n## 纯文本（连续版）\n")
    lines.append("".join(x["text"] for x in out))
    open(os.path.join(args.workdir, "全文逐字稿.md"), "w", encoding="utf-8").write("\n".join(lines))

    print("分句 %d 条 / 约 %d 字" % (len(out), sum(len(x["text"]) for x in out)))
    print("下一步：python build_article.py \"%s\"" % args.workdir)


if __name__ == "__main__":
    main()
