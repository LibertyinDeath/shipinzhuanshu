#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""batch_run.py —— 视频批量转写驱动模板（复制到项目工作目录，改 MANIFEST 即用）

功能：按清单逐视频执行四步流水线（抽音轨→转写→校正→成文），逐视频断点可续，
     已产出「文案_口语全文版.md」的视频自动跳过。

用法：
    python batch_run.py            # 跑全部未完成
    python batch_run.py --dry-run  # 只列清单不执行
    python batch_run.py --only 关键词

使用前改这三行：
    SRC   = 视频源目录
    BASE  = 转写工作目录（建议 <项目>/转写/{分组}/）
    MANIFEST = { "视频相对路径": ("分组", "工作目录名"), ... }
术语表：把项目术语表放 BASE/terms.tsv（TSV：错→对），自动挂载。
"""
import argparse
import glob
import os
import subprocess
import sys
from pathlib import Path

# ↓↓↓ 每个项目改这里 ↓↓↓
SRC = Path.home() / "Downloads/你的课程文件夹"
BASE = Path.home() / "WorkBuddy/你的项目/转写"
MANIFEST = {
    # "视频文件相对SRC路径.mp4": ("分组名", "工作目录名"),
    # "第1讲.mp4": ("正课", "第01讲-标题"),
}
# ↑↑↑ 改到这里 ↑↑↑

SKILL = Path(__file__).resolve().parent
PY = SKILL / ".venv/bin/python"          # 若 venv 不在技能目录，改成实际 venv python
TERMS = BASE / "terms.tsv"
TERMS_FALLBACK = SKILL.parent / "reference/术语表样例-过钱关.txt"


def find_mlx_model():
    """自动定位本地 whisper-large-v3-turbo snapshot（必须传本地路径，
    否则 mlx-whisper 联网校验版本会被代理挡死）。"""
    pats = glob.glob(os.path.expanduser(
        "~/.cache/huggingface/hub/models--mlx-community--whisper-large-v3-turbo/snapshots/*"))
    for d in pats:
        if (Path(d) / "model.safetensors").is_file() or (Path(d) / "weights.npz").is_file():
            return d
    return pats[0] if pats else "mlx-community/whisper-large-v3-turbo"


def run(cmd):
    print("$", " ".join(str(c) for c in cmd), flush=True)
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    for line in (r.stdout or "").strip().splitlines()[-3:]:
        print("   ", line, flush=True)
    if r.returncode != 0:
        print("   ✗ 失败：", (r.stderr or "").strip().splitlines()[-3:], flush=True)
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    terms = TERMS if TERMS.is_file() else TERMS_FALLBACK
    todo = []
    for rel, (group, name) in sorted(MANIFEST.items(), key=lambda kv: (kv[1][0], kv[1][1])):
        if args.only and args.only not in name:
            continue
        src = SRC / rel
        wd = BASE / group / name
        if not src.is_file():
            print("⚠ 源文件不存在：", rel)
            continue
        if (wd / "文案_口语全文版.md").is_file():
            print("✓ 已完成，跳过：", group, name)
            continue
        todo.append((src, wd, group, name))

    print("待处理 %d 个视频" % len(todo))
    if args.dry_run:
        for src, wd, g, n in todo:
            print(" -", g, n)
        return

    model_dir = find_mlx_model()
    ok = fail = 0
    for i, (src, wd, group, name) in enumerate(todo, 1):
        print("\n===== [%d/%d] %s / %s =====" % (i, len(todo), group, name), flush=True)
        wd.mkdir(parents=True, exist_ok=True)
        steps = [
            (PY, SKILL / "extract_audio.py", src, wd),
            (PY, SKILL / "mlx_transcribe.py", wd, "--model", model_dir),
            (PY, SKILL / "postprocess.py", wd, "--terms", terms),
            (PY, SKILL / "build_article.py", wd,
             "--title", name, "--source", "你的课程名"),
        ]
        good = True
        for k, cmd in enumerate(steps):
            # 已有切片则跳过抽音轨（断点续跑）
            if k == 0 and (wd / "meta.json").is_file() and list((wd / "chunks").glob("c_*.wav")):
                print("$ [跳过] extract_audio（已有切片）", flush=True)
                continue
            if not run(cmd):
                good = False
                break
        if good:
            ok += 1
            print("✓ 完成：", name, flush=True)
        else:
            fail += 1
            print("✗ 失败（可重跑续传）：", name, flush=True)

    print("\n全部结束：成功 %d，失败 %d" % (ok, fail))
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
