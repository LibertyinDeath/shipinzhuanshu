#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""transcribe.py —— 视频转文案 · 第 2 步：分片转写（faster-whisper，本机离线）

用法：
    python transcribe.py <工作目录> [--model 模型目录] [--threads N] [--limit N] [--force]

前置：extract_audio.py 已跑完（工作目录里有 chunks/ 与 meta.json）

输出：
    segments.jsonl       每行 {"i","start","end","text"}，逐片落盘，中断可续
    progress.json        已完成片号，重跑自动跳过

设计要点（实战踩过的坑，别改）：
- 逐片转写、逐片落盘：2 小时音频跑 30 分钟，中途崩了不至于全丢
- 不要用 BatchedInferencePipeline 一次喂多片：内存紧的机器直接 mkl_malloc failed
- 模型目录全自动探测；找不到就打印下载命令，不要静默失败
"""
import argparse
import glob
import json
import os
import platform
import sys


def find_model(explicit=None):
    if explicit:
        return explicit
    env = os.environ.get("V2T_MODEL")
    if env and os.path.isfile(os.path.join(env, "model.bin")):
        return env
    pats = [
        os.path.expanduser("~/.cache/huggingface/hub/models--Systran--faster-whisper-*/snapshots/*"),
        os.path.expanduser("~/.cache/whisper/**/snapshots/*"),
        os.path.expanduser("~/AI_Models/huggingface/**/models--Systran--faster-whisper-*/snapshots/*"),
        "D:/AI_Models/huggingface/**/models--Systran--faster-whisper-*/snapshots/*",
        "E:/AI_Models/huggingface/**/models--Systran--faster-whisper-*/snapshots/*",
        "C:/AI_Models/huggingface/**/models--Systran--faster-whisper-*/snapshots/*",
    ]
    hits = []
    for p in pats:
        for d in glob.glob(p, recursive=True):
            if os.path.isfile(os.path.join(d, "model.bin")):
                hits.append(d)
    if not hits:
        return None
    # 优先 small，其次 medium / large
    def rank(d):
        low = d.lower()
        for i, k in enumerate(("small", "medium", "large")):
            if "faster-whisper-" + k in low:
                return i
        return 9
    return sorted(hits, key=rank)[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--model")
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 片，用于试跑")
    ap.add_argument("--force", action="store_true", help="清空已有结果重跑")
    args = ap.parse_args()

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise SystemExit(
            "缺少 faster-whisper。安装（pip 索引不通时用镜像或离线包）：\n"
            "  pip install --no-deps --ignore-installed -i https://pypi.tuna.tsinghua.edu.cn/simple "
            "faster-whisper av ctranslate2 tokenizers huggingface_hub==0.25.2 onnxruntime"
        )

    model_dir = find_model(args.model)
    if not model_dir:
        raise SystemExit(
            "没找到本地 whisper 模型目录（需要有 model.bin 的那个 snapshot 目录）。\n"
            "下载 small 模型（约 480MB）：\n"
            "  set HF_ENDPOINT=https://hf-mirror.com && set HF_HUB_OFFLINE=0\n"
            "  python -c \"from huggingface_hub import snapshot_download;"
            "print(snapshot_download('Systran/faster-whisper-small'))\"\n"
            "国内可用魔搭或 hf-mirror；下好后用 --model 指定该目录。"
        )
    print("model:", model_dir)

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

    threads = args.threads or min(16, os.cpu_count() or 4)
    model = WhisperModel(model_dir, device="cpu", compute_type="int8", cpu_threads=threads)
    print("线程 %d，待处理 %d 片（已完成 %d）" % (threads, len(chunks), len(done)))

    PROMPT = ("以下是中文口播/课程讲稿。涉及术语：AI、智能体、大模型、私域、公域、流量、转化、短视频、"
              "直播间、知识付费、个人IP、OPC、一人公司。")
    idx = 0
    total = 0
    with open(out, "a", encoding="utf-8") as f:
        for cf in chunks:
            ci = int(os.path.basename(cf).split("_")[1].split(".")[0])
            if ci in done:
                continue
            offset = ci * chunk_sec
            segs, _info = model.transcribe(
                cf, language="zh", beam_size=5, initial_prompt=PROMPT,
                vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500),
                condition_on_previous_text=False,
            )
            cnt = 0
            for s in segs:
                idx += 1
                total += 1
                cnt += 1
                f.write(json.dumps({"i": idx, "start": round(offset + s.start, 2),
                                    "end": round(offset + s.end, 2), "text": s.text},
                                   ensure_ascii=False) + "\n")
            f.flush()
            done.append(ci)
            json.dump({"done": sorted(set(done))}, open(prog, "w", encoding="utf-8"))
            print("片 %d 完成，%d 段，累计 %d 段" % (ci, cnt, total), flush=True)

    print("转写完成 → %s" % out)
    print("下一步：python postprocess.py \"%s\"" % args.workdir)


if __name__ == "__main__":
    main()
