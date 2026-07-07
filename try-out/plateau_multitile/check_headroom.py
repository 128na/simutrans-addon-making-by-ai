"""
レンダリング済みの合成画像が、tilecutterの各タイル抽出ウィンドウの範囲内に
収まっているか（上端が見切れていないか）を検証するツール。

各ピクセル列(x座標)について、その列をカバーするタイルのうち最も上端が高い
(top値が最小の)ものを求め、そのtopより上に不透明ピクセルが存在しないかを
チェックする(=どのタイルにも回収されず失われるピクセルがないか)。
"""
import argparse

from PIL import Image
import numpy as np

PAKSIZE = 128


def tile_to_screen(xpos, ypos, xdims, ydims, p, screen_height):
    xx = (xdims - 1 - xpos + ypos) * (p // 2)
    yy = ((xdims - xpos) + (ydims - ypos)) * (p // 4) + (p // 2)
    return xx, screen_height - yy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    parser.add_argument("--dims-x", type=int, required=True)
    parser.add_argument("--dims-y", type=int, required=True)
    args = parser.parse_args()

    img = Image.open(args.image).convert("RGBA")
    arr = np.array(img)
    alpha = arr[:, :, 3]
    height, width = alpha.shape

    min_top_per_col = np.full(width, np.inf)
    for x in range(args.dims_x):
        for y in range(args.dims_y):
            left, top = tile_to_screen(x, y, args.dims_x, args.dims_y, PAKSIZE, height)
            left_c = max(0, left)
            right_c = min(width, left + PAKSIZE)
            if left_c >= right_c:
                continue
            min_top_per_col[left_c:right_c] = np.minimum(min_top_per_col[left_c:right_c], top)

    worst_clip = 0
    worst_col = None
    for col in range(width):
        top = min_top_per_col[col]
        if not np.isfinite(top):
            continue
        col_alpha = alpha[:, col]
        ys = np.where(col_alpha > 10)[0]
        if len(ys) == 0:
            continue
        content_top = int(ys.min())
        clip = top - content_top
        if clip > worst_clip:
            worst_clip = clip
            worst_col = col

    if worst_col is None:
        print("OK (no clipping found in any column)")
        return
    print(f"worst_col={worst_col} clip_amount={worst_clip:.0f}px "
          f"{'CLIPPED' if worst_clip > 0 else 'OK'}")


if __name__ == "__main__":
    main()
