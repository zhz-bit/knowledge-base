#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把苹果灰度图渲染成「每个像素格子按灰度上色 + 格内标注灰度数值」的可视化，
类似经典的 Lincoln 像素矩阵示意图。
依赖: numpy, matplotlib
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

M = np.load("apple_gray_matrix.npy")        # (216, 224) uint8
mask = np.loadtxt("apple_mask_matrix.csv", delimiter=",").astype(bool)
H, W = M.shape


def block_downsample(a, cols):
    """按块平均把图缩到约 cols 列宽，返回 (整数灰度块, 行数, 列数)。"""
    step = max(1, round(W / cols))
    nh, nw = H // step, W // step
    a = a[:nh * step, :nw * step].reshape(nh, step, nw, step)
    small = a.mean(axis=(1, 3))
    return np.round(small).astype(int), nh, nw, step


def render(gray_small, fname, title, cell=0.5, fontsize=6):
    nh, nw = gray_small.shape
    fig, ax = plt.subplots(figsize=(nw * cell, nh * cell), dpi=150)
    ax.imshow(gray_small, cmap="gray", vmin=0, vmax=255,
              interpolation="nearest", aspect="equal")
    for i in range(nh):
        for j in range(nw):
            v = int(gray_small[i, j])
            ax.text(j, i, str(v), ha="center", va="center",
                    fontsize=fontsize,
                    color="white" if v < 128 else "black")
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(title, fontsize=12)
    # 细网格线
    ax.set_xticks(np.arange(-0.5, nw, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, nh, 1), minor=True)
    ax.grid(which="minor", color="#888", linewidth=0.3)
    fig.tight_layout()
    fig.savefig(fname, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {fname}  grid={nh}x{nw}")


# 1) 全图降采样到约 32 列
small32, nh, nw, step = block_downsample(M, cols=32)
render(small32, "apple_pixel_matrix_full.png",
       f"Apple grayscale pixel matrix  (~1/{step} downsample, {nh}x{nw})",
       cell=0.55, fontsize=6.5)

# 2) 裁剪到苹果包围盒后再降采样，数值更聚焦在苹果上
ys, xs = np.where(mask)
y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
crop = M[y0:y1, x0:x1]
ch, cw = crop.shape
step2 = max(1, round(cw / 30))
nh2, nw2 = ch // step2, cw // step2
cropd = crop[:nh2 * step2, :nw2 * step2].reshape(nh2, step2, nw2, step2)
cropd = np.round(cropd.mean(axis=(1, 3))).astype(int)
render(cropd, "apple_pixel_matrix_crop.png",
       f"Apple (cropped) grayscale pixel matrix  ({nh2}x{nw2})",
       cell=0.6, fontsize=7)
