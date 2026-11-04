#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""extract_audio.py —— 视频转文案 · 第 1 步：探针 + 抽音轨 + 切片

用法：
    python extract_audio.py <视频文件> <工作目录> [--chunk 600] [--force]

输出（全部落在工作目录）：
    meta.json        时长/流信息/切片清单
    audio16k.wav     16kHz 单声道 PCM（ASR 友好）
    chunks/c_000.wav 按 N 秒切片（默认 600s，防整段解码 OOM）

设计要点：
- ffmpeg/ffprobe 全自动探测：环境变量 → PATH → 常见安装目录，不写死本机路径
- 切片是硬要求：2 小时音频整段解码约 480MB float32，内存紧张的机器直接 MemoryError
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys


def find_bin(name):
    """探测可执行文件，返回绝对路径或 None。"""
    env = os.environ.get("FFMPEG_HOME") or os.environ.get("FFMPEG_BIN")
    if env:
        for cand in (os.path.join(env, name), os.path.join(env, name + ".exe")):
            if os.path.isfile(cand):
                return cand
    hit = shutil.which(name)
    if hit:
        return hit
    patterns = [
        os.path.expanduser("~/ffmpeg/bin/" + name + "*"),
        os.path.expanduser("~/.workbuddy/binaries/ffmpeg/**/" + name + "*"),
        "C:/ffmpeg/**/" + name + ".exe",
        "C:/ffmpeg/bin/" + name + ".exe",
        "D:/ffmpeg/**/" + name + ".exe",
        "/usr/local/bin/" + name,
        "/opt/homebrew/bin/" + name,
    ]
    for p in patterns:
        for f in glob.glob(p, recursive=True):
            if os.path.isfile(f):
                return f
    return None


def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        sys.stderr.write(r.stderr.decode("utf-8", "replace")[-2000:])
        raise SystemExit("命令失败，退出码 %d：%s" % (r.returncode, " ".join(cmd[:3])))
    return r.stdout.decode("utf-8", "replace")


def probe(ffprobe, video):
    out = run([
        ffprobe, "-v", "error",
        "-show_entries", "format=duration,size,bit_rate",
        "-show_entries", "stream=index,codec_type,codec_name,width,height,sample_rate,channels",
        "-of", "json", video,
    ])
    data = json.loads(out)
    streams = data.get("streams", [])
    fmt = data.get("format", {})
    dur = float(fmt.get("duration") or 0)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    has_subs = any(s.get("codec_type") == "subtitle" for s in streams)
    return {"duration": round(dur, 2), "size": fmt.get("size"),
            "streams": streams, "has_audio": has_audio, "has_subtitle": has_subs}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("workdir")
    ap.add_argument("--chunk", type=int, default=600, help="切片秒数，默认 600")
    ap.add_argument("--force", action="store_true", help="重跑，覆盖已有切片")
    args = ap.parse_args()

    ffmpeg = find_bin("ffmpeg")
    ffprobe = find_bin("ffprobe")
    if not ffmpeg or not ffprobe:
        raise SystemExit("找不到 ffmpeg/ffprobe。安装后重试，或设置环境变量 FFMPEG_HOME 指向 bin 目录。")
    print("ffmpeg :", ffmpeg)
    print("ffprobe:", ffprobe)

    if not os.path.isfile(args.video):
        raise SystemExit("视频不存在：%s" % args.video)

    os.makedirs(args.workdir, exist_ok=True)
    meta = probe(ffprobe, args.video)
    print("时长 %.1f 秒 / %.1f 分钟" % (meta["duration"], meta["duration"] / 60))
    if not meta["has_audio"]:
        raise SystemExit("这个文件没有音轨，无法转写（纯画面视频只能走 OCR 字幕路线）。")
    if meta["has_subtitle"]:
        print("提示：检测到内嵌字幕流，可先用 ffmpeg -map 0:s:0 直接抽 SRT，比 ASR 更准。")

    wav = os.path.join(args.workdir, "audio16k.wav")
    if args.force or not os.path.isfile(wav):
        print("抽音轨 → 16kHz 单声道 …")
        run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", args.video,
             "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav])
    print("wav 大小 %.1f MB" % (os.path.getsize(wav) / 1024 / 1024))

    chunks_dir = os.path.join(args.workdir, "chunks")
    if args.force and os.path.isdir(chunks_dir):
        shutil.rmtree(chunks_dir)
    os.makedirs(chunks_dir, exist_ok=True)
    existing = sorted(glob.glob(os.path.join(chunks_dir, "c_*.wav")))
    expect = int(meta["duration"] // args.chunk) + 1
    if len(existing) < expect:
        print("切片（每 %d 秒）…" % args.chunk)
        run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", wav,
             "-f", "segment", "-segment_time", str(args.chunk),
             "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
             os.path.join(chunks_dir, "c_%03d.wav")])
    chunks = sorted(glob.glob(os.path.join(chunks_dir, "c_*.wav")))

    meta.update({"video": os.path.abspath(args.video), "wav": wav,
                 "chunk_sec": args.chunk, "chunks": len(chunks)})
    with open(os.path.join(args.workdir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print("切片 %d 个，meta.json 已写入" % len(chunks))
    print("下一步：python transcribe.py \"%s\"" % args.workdir)


if __name__ == "__main__":
    main()
