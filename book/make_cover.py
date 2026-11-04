#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""make_cover.py —— 生成《过钱关·创富智慧》封面（1200x1800，墨底鎏金竖排三大字）"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "cover.png"
SONG = "/System/Library/Fonts/Supplemental/Songti.ttc"

W, H = 1200, 1800
GOLD = (217, 185, 108)
GOLD_DIM = (196, 165, 90)
BG_TOP = (24, 29, 36)
BG_BOT = (10, 13, 17)
RED = (159, 42, 34)

def font(path, size, index=0):
    return ImageFont.truetype(path, size, index=index)

def probe():
    """找出 Songti.ttc 里 Black 字重的 index。"""
    for i in range(8):
        try:
            f = font(SONG, 40, i)
            print(i, f.getname())
        except Exception:
            break

def main():
    probe()
    img = Image.new("RGB", (W, H), BG_TOP)
    d = ImageDraw.Draw(img)
    # 背景纵向渐变
    for y in range(H):
        t = y / H
        c = tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOT))
        d.line([(0, y), (W, y)], fill=c)
    # 竖排三大字（过 / 钱 / 关）
    f_big = font(SONG, 380, BLACK_IDX)
    f_seal = font(SONG, 64, BLACK_IDX)
    f_mid = font(SONG, 58, BOLD_IDX)
    f_small = font(SONG, 40, REG_IDX)
    f_tiny = font(SONG, 33, REG_IDX)

    for i, ch in enumerate(["过", "钱", "关"]):
        cx, cy = W // 2, 350 + i * 430
        # 阴影
        d.text((cx + 8, cy + 10), ch, font=f_big, fill=(0, 0, 0), anchor="mm")
        d.text((cx, cy), ch, font=f_big, fill=GOLD, anchor="mm")

    # 顶部小字：创富智慧
    d.text((W // 2, 100), "创 富 智 慧", font=f_mid, fill=GOLD_DIM, anchor="mm")

    # 双线金框（古籍感）
    d.rectangle([52, 52, W - 52, H - 52], outline=GOLD_DIM, width=3)
    d.rectangle([66, 66, W - 66, H - 66], outline=(120, 100, 62), width=1)

    # 印章（右下）：剽悍 著
    sw, sh, sx, sy = 150, 150, W - 250, H - 400
    d.rectangle([sx, sy, sx + sw, sy + sh], fill=RED)
    d.rectangle([sx + 10, sy + 10, sx + sw - 10, sy + sh - 10], outline=(230, 210, 190), width=2)
    d.text((sx + sw / 2, sy + 42), "剽悍", font=f_seal, fill=(245, 235, 220), anchor="mm")
    d.text((sx + sw / 2, sy + 108), "著", font=f_seal, fill=(245, 235, 220), anchor="mm")

    # 中下：主讲人
    d.text((W // 2, H - 190), "剽悍一只猫 · 课程主讲", font=f_small, fill=GOLD_DIM, anchor="mm")
    d.text((W // 2, H - 130), "忠实原意整理版 · 试读版 卷一", font=f_tiny,
           fill=(150, 135, 105), anchor="mm")

    img.save(OUT)
    print("封面已生成：", OUT)

BLACK_IDX = 0
BOLD_IDX = 1
REG_IDX = 6

if __name__ == "__main__":
    main()
