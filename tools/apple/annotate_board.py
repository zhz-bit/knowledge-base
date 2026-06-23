#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在井字棋照片上标注 X / O 与 9 个棋盘位置，并输出棋盘状态示意图。"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from PIL import Image

img = np.asarray(Image.open("image.png").convert("RGB"))

# 棋盘网格边界（原图像素坐标，已经过对齐校验）
xs = [138, 161, 184, 207]     # 列边界
ys = [145, 170, 195, 220]     # 行边界
xc = [(xs[i] + xs[i + 1]) / 2 for i in range(3)]   # 列中心
yc = [(ys[i] + ys[i + 1]) / 2 for i in range(3)]   # 行中心

# 棋盘状态: 'X'=粉色花块, 'O'=木环, '' =空
#   位置编号        列
#   1 2 3      R1: X . O
#   4 5 6      R2: . X .
#   7 8 9      R3: . . .
board = [["X", "",  "O"],
         ["",  "X", ""],
         ["",  "",  ""]]

fig, (ax, ax2) = plt.subplots(1, 2, figsize=(13, 6),
                              gridspec_kw={"width_ratios": [1.4, 1]})

# ---------- 左：照片标注 ----------
ax.imshow(img)
for x in xs:
    ax.plot([x, x], [ys[0], ys[-1]], color="red", lw=1.5)
for y in ys:
    ax.plot([xs[0], xs[-1]], [y, y], color="red", lw=1.5)

pos = 1
for r in range(3):
    for c in range(3):
        # 位置编号（格子左上角小标）
        ax.text(xs[c] + 2, ys[r] + 2, str(pos), color="yellow",
                fontsize=9, fontweight="bold", va="top", ha="left")
        v = board[r][c]
        if v == "X":
            ax.text(xc[c], yc[r], "X", color="magenta", fontsize=22,
                    fontweight="bold", ha="center", va="center")
        elif v == "O":
            ax.text(xc[c], yc[r], "O", color="deepskyblue", fontsize=22,
                    fontweight="bold", ha="center", va="center")
        pos += 1
ax.set_title("Annotated photo  (X = pink piece, O = wooden ring)", fontsize=12)
ax.set_xticks([]); ax.set_yticks([])

# ---------- 右：棋盘状态示意图 ----------
ax2.set_xlim(0, 3); ax2.set_ylim(0, 3); ax2.set_aspect("equal")
ax2.invert_yaxis()
for i in range(4):
    ax2.plot([i, i], [0, 3], color="black", lw=2)
    ax2.plot([0, 3], [i, i], color="black", lw=2)
pos = 1
for r in range(3):
    for c in range(3):
        ax2.text(c + 0.06, r + 0.06, str(pos), color="gray",
                 fontsize=11, va="top", ha="left")
        v = board[r][c]
        if v == "X":
            ax2.text(c + 0.5, r + 0.5, "X", color="magenta", fontsize=40,
                     fontweight="bold", ha="center", va="center")
        elif v == "O":
            ax2.text(c + 0.5, r + 0.5, "O", color="dodgerblue", fontsize=40,
                     fontweight="bold", ha="center", va="center")
        pos += 1
ax2.set_title("Board state", fontsize=12)
ax2.set_xticks([]); ax2.set_yticks([])

fig.tight_layout()
fig.savefig("board_annotated.png", dpi=150, bbox_inches="tight")
print("saved board_annotated.png")

# 控制台同时打印棋盘
print("\n位置编号          棋盘状态")
print(" 1 | 2 | 3        {} | {} | {}".format(*[v or '.' for v in board[0]]))
print("---+---+---       ---+---+---")
print(" 4 | 5 | 6        {} | {} | {}".format(*[v or '.' for v in board[1]]))
print("---+---+---       ---+---+---")
print(" 7 | 8 | 9        {} | {} | {}".format(*[v or '.' for v in board[2]]))
