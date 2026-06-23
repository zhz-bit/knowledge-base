#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apple.png のリンゴを分割（セグメンテーション）し、
グレースケール画素行列を書き出すスクリプト。

依存: numpy, Pillow のみ（cv2 / scipy 不要）
"""
import numpy as np
from PIL import Image

SRC = "apple.png"

# ---------- 1. 読み込み ----------
im = Image.open(SRC)
print("入力:", im.size, im.mode)

# RGBA の場合、白背景に合成して RGB にする（透過の有無に関わらず安定）
rgba = im.convert("RGBA")
arr = np.asarray(rgba).astype(np.float64)
alpha = arr[..., 3]
rgb_raw = arr[..., :3]
# 白背景合成
a = (alpha / 255.0)[..., None]
rgb = rgb_raw * a + 255.0 * (1.0 - a)
rgb_u8 = rgb.astype(np.uint8)
H, W = rgb_u8.shape[:2]

# ---------- 2. グレースケール ----------
# ITU-R 601 輝度（PIL convert('L') と同一）
gray = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2])
gray_u8 = np.clip(np.round(gray), 0, 255).astype(np.uint8)

# ---------- 3. 背景判定（白っぽい & 低彩度）----------
R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
mx = np.maximum(np.maximum(R, G), B)
mn = np.minimum(np.minimum(R, G), B)
sat = mx - mn                      # 彩度の代理（0=無彩色）
whiteish = (mn > 200) & (sat < 35) # 明るくて色味が無い = 背景候補

# 既存アルファがマスクとして使えるなら、それも背景候補に反映
if alpha.min() < 250:
    whiteish = whiteish | (alpha < 128)

# ---------- 4. 枠からのフラッドフィルで「外側の背景」を確定 ----------
# （リンゴ内部の白ハイライトを背景として誤除去しないため）
bg = np.zeros((H, W), dtype=bool)
stack = []
for x in range(W):
    for y in (0, H - 1):
        if whiteish[y, x] and not bg[y, x]:
            bg[y, x] = True
            stack.append((y, x))
for y in range(H):
    for x in (0, W - 1):
        if whiteish[y, x] and not bg[y, x]:
            bg[y, x] = True
            stack.append((y, x))

while stack:
    y, x = stack.pop()
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        ny, nx = y + dy, x + dx
        if 0 <= ny < H and 0 <= nx < W and whiteish[ny, nx] and not bg[ny, nx]:
            bg[ny, nx] = True
            stack.append((ny, nx))

mask = ~bg  # リンゴ前景

# ---------- 5. 軽いクリーンアップ（穴埋め）----------
# マスク内部の小さな穴（背景に連結していない非マスク画素）を前景化
hole_bg = np.zeros((H, W), dtype=bool)
notmask = ~mask
stack = []
for x in range(W):
    for y in (0, H - 1):
        if notmask[y, x] and not hole_bg[y, x]:
            hole_bg[y, x] = True
            stack.append((y, x))
for y in range(H):
    for x in (0, W - 1):
        if notmask[y, x] and not hole_bg[y, x]:
            hole_bg[y, x] = True
            stack.append((y, x))
while stack:
    y, x = stack.pop()
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        ny, nx = y + dy, x + dx
        if 0 <= ny < H and 0 <= nx < W and notmask[ny, nx] and not hole_bg[ny, nx]:
            hole_bg[ny, nx] = True
            stack.append((ny, nx))
holes = notmask & ~hole_bg   # 外側背景に届かない穴
mask = mask | holes

mask_u8 = (mask.astype(np.uint8)) * 255
coverage = mask.mean() * 100

# ---------- 6. 保存 ----------
Image.fromarray(gray_u8, mode="L").save("apple_gray.png")
Image.fromarray(mask_u8, mode="L").save("apple_mask.png")

# 背景を透過にした切り抜き
cutout = np.dstack([rgb_u8, mask_u8])
Image.fromarray(cutout, mode="RGBA").save("apple_cutout.png")

# マスク内のみグレー値、外は 0
gray_masked = np.where(mask, gray_u8, 0).astype(np.uint8)
Image.fromarray(gray_masked, mode="L").save("apple_gray_masked.png")

# 全画素グレー行列（CSV + npy）
np.savetxt("apple_gray_matrix.csv", gray_u8, fmt="%d", delimiter=",")
np.save("apple_gray_matrix.npy", gray_u8)
np.savetxt("apple_mask_matrix.csv", mask.astype(np.uint8), fmt="%d", delimiter=",")

# ---------- 7. コンソール出力 ----------
print(f"\nグレー行列 shape = {gray_u8.shape}  (H={H}, W={W})")
print(f"グレー値レンジ: min={gray_u8.min()}  max={gray_u8.max()}  mean={gray_u8.mean():.1f}")
print(f"リンゴ画素数: {int(mask.sum())} / {H*W}  (被覆率 {coverage:.1f}%)")

# 全行列はターミナルに出すと巨大なので、ダウンサンプルしたプレビューを表示
def preview(matrix, title, step_target=28):
    sy = max(1, matrix.shape[0] // step_target)
    sx = max(1, matrix.shape[1] // step_target)
    small = matrix[::sy, ::sx]
    print(f"\n{title}  (1/{sy}x1/{sx} 間引き, 表示 shape={small.shape})")
    np.set_printoptions(linewidth=200, threshold=10_000)
    print(small)
    return small

preview(gray_u8, "■ グレースケール画素行列プレビュー")

# マスクの ASCII プレビュー
sy = max(1, H // 40); sx = max(1, W // 80)
ascii_mask = mask[::sy, ::sx]
print("\n■ 分割マスク ASCII プレビュー (#=リンゴ, ' '=背景)")
for row in ascii_mask:
    print("".join("#" if v else " " for v in row))

print("\n保存済みファイル:")
for f in ["apple_gray.png", "apple_mask.png", "apple_cutout.png",
          "apple_gray_masked.png", "apple_gray_matrix.csv",
          "apple_gray_matrix.npy", "apple_mask_matrix.csv"]:
    print("  -", f)
