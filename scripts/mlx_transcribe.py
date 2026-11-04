#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""mlx_transcribe.py —— 视频转文案 · 第 2 步（Mac 版：mlx-whisper，Metal GPU 加速）

与 faster-whisper 版 transcribe.py 输出完全兼容：
    segments.jsonl   每行 {"i","start","end","text"}
    progress.json    已完成片号，中断续跑

用法：
    python mlx_transcribe.py <工作目录> [--model <HF模型ID或本地目录>] [--limit N] [--force]

依赖：pip install mlx-whisper；模型默认 mlx-community/whisper-large-v3-turbo
"""
import argparse
import glob
import json
import os
import time

DEFAULT_REPO = "mlx-community/whisper-large-v3-turbo"
PROMPT = ("以下是中文口播/课程讲稿。涉及术语：AI、智能体、大模型、私域、公域、流量、转化、短视频、"
          "直播间、知识付费、个人IP、OPC、一人公司、猫叔、过钱关、创富智慧、吸金作者、人间王炸。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--model", default=DEFAULT_REPO)
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 片，用于试跑")
    ap.add_argument("--force", action="store_true", help="清空已有结果重跑")
    ap.add_argument("--beam", type=int, default=5)
    args = ap.parse_args()

    try:
        import mlx_whisper
    except ImportError:
        raise SystemExit("缺少 mlx-whisper：pip install mlx-whisper")

    chunks = sorted(glob.glob(os.path.join(args.workdir, "chunks", "c_*.wav")))
    if not chunks:
        raise SystemExit("工作目录里没有 chunks/，先跑 extract_audio.py")
    meta = {}
    mp = os.path.join(args.workdir, "meta.json")
    if os.path.isfile(mp):
        meta = json.load(open(mp, encoding="utf-8"))
    chunk_sec = int(meta.get("chunk_sec") or 600)
    if args.limit:
        chunks = chunks[: args.limit]

    out = os.path.join(args.workdir, "segments.jsonl")
    prog = os.path.join(args.workdir, "progress.json")
    done = []
    if args.force:
        open(out, "w", encoding="utf-8").close()
        done = []
    elif os.path.isfile(prog):
        try:
            done = json.load(open(prog, encoding="utf-8")).get("done", [])
        except Exception:
            done = []

    print("模型: %s，待处理 %d 片（已完成 %d）" % (args.model, len(chunks), len(done)), flush=True)
    idx = 0
    total = 0
    t_start = time.time()
    with open(out, "a", encoding="utf-8") as f:
        for cf in chunks:
            ci = int(os.path.basename(cf).split("_")[1].split(".")[0])
            if ci in done:
                continue
            offset = ci * chunk_sec
            t0 = time.time()
            result = mlx_whisper.transcribe(
                cf, path_or_hf_repo=args.model, language="zh",
                initial_prompt=PROMPT, condition_on_previous_text=False,
                temperature=0.0,
            )
            dur = result.get("segments") and result["segments"][-1].get("end", 0) or 0
            rtf = (time.time() - t0) / dur if dur else 0
            cnt = 0
            for s in result.get("segments", []):
                idx += 1
                total += 1
                cnt += 1
                f.write(json.dumps({"i": idx, "start": round(offset + float(s["start"]), 2),
                                    "end": round(offset + float(s["end"]), 2),
                                    "text": s["text"]}, ensure_ascii=False) + "\n")
            f.flush()
            done.append(ci)
            json.dump({"done": sorted(set(done))}, open(prog, "w", encoding="utf-8"))
            print("片 %d 完成：音频 %.0f 秒，耗时 %.0f 秒，RTF %.3f，%d 段，累计 %d 段"
                  % (ci, dur, time.time() - t0, rtf, cnt, total), flush=True)

    el = time.time() - t_start
    print("转写完成 → %s（本批总耗时 %.0f 秒）" % (out, el))
    print("下一步：python postprocess.py \"%s\"" % args.workdir)


if __name__ == "__main__":
    main()
